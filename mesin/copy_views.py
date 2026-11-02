import pythoncom
import win32com.client
import json
import re
import io
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from datetime import datetime, timedelta

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils.timezone import now

from .models import Device, AdminLog

# ==========================================
# 1. SISTEM LOGGING OTOMATIS & PEMBERSIHAN
# ==========================================
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def record_log(request, action_text):
    """Mencatat aktivitas dan menghapus log yang usianya lebih dari 30 hari (Sebulan)."""
    if request.user.is_authenticated:
        ip = get_client_ip(request)
        AdminLog.objects.create(user=request.user, ip_address=ip, action=action_text)
        
        # Auto-delete log lama (> 30 hari) agar database tidak bengkak
        batas_waktu = now() - timedelta(days=30)
        AdminLog.objects.filter(timestamp__lt=batas_waktu).delete()

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    record_log(request, "Login ke dalam sistem")

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    record_log(request, "Logout dari sistem")


# ==========================================
# 2. HALAMAN UTAMA & AUTH
# ==========================================
def index_view(request):
    return render(request, 'index.html')

# @csrf_exempt
def api_login(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user = authenticate(request, username=data.get('username'), password=data.get('password'))
        if user is not None:
            login(request, user)
            return JsonResponse({'message': 'Login berhasil'})
        return JsonResponse({'error': 'Username atau password salah'}, status=401)
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# @csrf_exempt
def api_logout(request):
    logout(request)
    return JsonResponse({'message': 'Logout berhasil'})


# ==========================================
# 3. MANAJEMEN ADMIN & LOGS
# ==========================================
# @csrf_exempt
def handle_admins(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
        
    if request.method == 'GET':
        admins = list(User.objects.values('id', 'username', 'first_name', 'date_joined', 'is_superuser'))
        for a in admins:
            a['date_joined'] = a['date_joined'].strftime("%Y-%m-%d %H:%M:%S")
        return JsonResponse({'admins': admins})
        
    elif request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        nama_lengkap = data.get('nama_lengkap', '').strip()
        password = data.get('password', '')
        
        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username sudah digunakan'}, status=400)
            
        User.objects.create_user(username=username, password=password, first_name=nama_lengkap)
        record_log(request, f"Membuat akun admin baru: {username}")
        return JsonResponse({'message': 'Admin berhasil ditambahkan'})

# @csrf_exempt
def delete_admin(request, admin_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
        
    if request.method == 'DELETE':
        if request.user.id == admin_id:
            return JsonResponse({'error': 'Tidak dapat menghapus akun Anda sendiri.'}, status=400)
            
        try:
            admin = User.objects.get(id=admin_id)
            target_uname = admin.username
            admin.delete()
            record_log(request, f"Menghapus akun admin: {target_uname}")
            return JsonResponse({'message': 'Admin berhasil dihapus'})
        except User.DoesNotExist:
            return JsonResponse({'error': 'Admin tidak ditemukan'}, status=404)

# @csrf_exempt
def get_logs(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
        
    if request.method == 'GET':
        logs = AdminLog.objects.select_related('user').order_by('-timestamp')[:300]
        data = []
        for l in logs:
            data.append({
                "username": l.user.username if l.user else "Sistem",
                "ip": l.ip_address or "Local",
                "action": l.action,
                "waktu": l.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            })
        return JsonResponse({'logs': data})


# ==========================================
# 4. KONEKSI MESIN (ZKTECO)
# ==========================================
def _get_comm_key(dev):
    try:
        return int(dev.comm_key) if dev.comm_key is not None else 0
    except (ValueError, TypeError):
        return 0

def clean_string(val):
    if not isinstance(val, str): return str(val)
    return re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', val)

# @csrf_exempt
def handle_devices(request):
    if request.method == 'GET':
        devices = [d.to_dict() for d in Device.objects.all()]
        return JsonResponse({"devices": devices, "active_id": None})
    
    elif request.method == 'POST':
        data = json.loads(request.body)
        raw_key = data.get("comm_key", 0)
        try:
            comm_key = int(raw_key) if raw_key not in (None, "") else 0
        except (ValueError, TypeError):
            comm_key = 0

        ip = data.get("ip")
        port = int(data.get("port", 4370))
        nama_mesin = data.get("name", "")

        pythoncom.CoInitialize()
        try:
            zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
            zk.SetCommPassword(comm_key)
            if not zk.Connect_Net(ip, port):
                return JsonResponse({"error": "Gagal terhubung ke mesin."}, status=400)
            
            users = []
            zk.EnableDevice(1, False)
            if zk.ReadAllUserID(1):
                sEnrollNumber, sName, sPassword, iPrivilege, bEnabled = "", "", "", 0, True
                while True:
                    status, sEnrollNumber, sName, sPassword, iPrivilege, bEnabled = zk.SSR_GetAllUserInfo(1, sEnrollNumber, sName, sPassword, iPrivilege, bEnabled)
                    if not status: break
                    users.append({
                        "user_id": clean_string(sEnrollNumber).strip(),
                        "nama": clean_string(sName).strip(),
                        "role": "Admin" if iPrivilege != 0 else "User",
                        "kode_privilege": iPrivilege,
                        "enabled": bEnabled
                    })
            zk.EnableDevice(1, True)
            zk.Disconnect()
        except Exception as e:
            return JsonResponse({"error": f"Error koneksi mesin: {str(e)}"}, status=500)
        finally:
            pythoncom.CoUninitialize()

        device = Device.objects.create(name=nama_mesin, ip=ip, port=port, comm_key=comm_key)
        record_log(request, f"Mendaftarkan mesin baru: {nama_mesin or ip}")
        return JsonResponse({"device": device.to_dict(), "users": users})

# @csrf_exempt
def device_detail(request, dev_id):
    try:
        dev = Device.objects.get(id=dev_id)
    except Device.DoesNotExist:
        return JsonResponse({"error": "Mesin tidak ditemukan"}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            dev.name = data.get("name", dev.name)
            dev.ip = data.get("ip", dev.ip)
            dev.port = int(data.get("port", dev.port))
            if "comm_key" in data and data.get("comm_key") is not None:
                raw_key = data.get("comm_key")
                dev.comm_key = int(raw_key) if raw_key != "" else 0
            dev.save()
            record_log(request, f"Mengubah konfigurasi mesin: {dev.name or dev.ip}")
            return JsonResponse({"message": "Konfigurasi mesin diperbarui", "device": dev.to_dict()})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    elif request.method == 'DELETE':
        ip_mesin = dev.ip
        dev.delete()
        record_log(request, f"Menghapus mesin dari sistem: {ip_mesin}")
        return JsonResponse({"message": "Mesin berhasil dihapus"})

    return JsonResponse({"error": "Method not allowed"}, status=405)

# @csrf_exempt
def connect_device(request, dev_id):
    if request.method == 'POST':
        try:
            dev = Device.objects.get(id=dev_id)
            users, err = _get_users_from_machine(dev)
            if err: return JsonResponse({"error": err}, status=400)
            record_log(request, f"Terhubung (Sinkron) dengan mesin {dev.ip}")
            return JsonResponse({"device": dev.to_dict(), "users": users})
        except Device.DoesNotExist:
            return JsonResponse({"error": "Mesin tidak ditemukan"}, status=404)

# @csrf_exempt
def handle_users(request, dev_id):
    if request.method == 'GET':
        try:
            dev = Device.objects.get(id=dev_id)
            users, err = _get_users_from_machine(dev)
            if err: return JsonResponse({"error": err}, status=400)
            record_log(request, f"Me-refresh data karyawan dari mesin {dev.ip}")
            return JsonResponse({"users": users})
        except Device.DoesNotExist:
            return JsonResponse({"error": "Mesin tidak ditemukan"}, status=404)

# @csrf_exempt
def modify_user(request, dev_id, pin):
    try:
        dev = Device.objects.get(id=dev_id)
    except Device.DoesNotExist:
        return JsonResponse({"error": "Mesin tidak ditemukan"}, status=404)
    
    pythoncom.CoInitialize()
    try:
        zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
        zk.SetCommPassword(_get_comm_key(dev))
        if not zk.Connect_Net(dev.ip, dev.port):
            return JsonResponse({"error": "Gagal terhubung ke mesin."}, status=500)
        
        zk.EnableDevice(1, False)

        if request.method == 'PUT':
            try:
                data = json.loads(request.body)
                nama = str(data.get("nama", ""))[:24] 
                privilege = int(data.get("privilege", 0))
                enabled = bool(data.get("enabled", True)) 
                
                status = zk.SSR_SetUserInfo(1, str(pin), nama, "", privilege, enabled)
                zk.RefreshData(1)
                
                users = _fetch_users_direct(zk)
                zk.EnableDevice(1, True)
                zk.Disconnect()
                
                if status:
                    record_log(request, f"Mengedit karyawan ID {pin} (Nama: {nama}) di mesin {dev.ip}")
                    return JsonResponse({"message": "User diperbarui", "users": users})
                else:
                    return JsonResponse({"error": "Gagal menyimpan ke mesin."}, status=500)
            except Exception as e:
                zk.EnableDevice(1, True)
                zk.Disconnect()
                return JsonResponse({"error": str(e)}, status=500)
                
        elif request.method == 'DELETE':
            zk.SSR_SetUserInfo(1, str(pin), "", "", 0, True)
            status = zk.SSR_DeleteEnrollData(1, str(pin), 12)
            zk.RefreshData(1)
            
            users = _fetch_users_direct(zk)
            zk.EnableDevice(1, True)
            zk.Disconnect()
            if status: 
                record_log(request, f"Menghapus karyawan ID {pin} dari mesin {dev.ip}")
                return JsonResponse({"message": "User dihapus", "users": users})
            return JsonResponse({"error": "Gagal menghapus data."}, status=500)

    finally:
        pythoncom.CoUninitialize()


# @csrf_exempt
def batch_update_users(request, dev_id):
    if request.method != 'POST': return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        dev = Device.objects.get(id=dev_id)
        data = json.loads(request.body)
        updates = data.get("updates", [])
    except: return JsonResponse({"error": "Format/Mesin tidak valid."}, status=400)
    
    if not updates: return JsonResponse({"error": "Tidak ada data."}, status=400)

    pythoncom.CoInitialize()
    try:
        zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
        zk.SetCommPassword(_get_comm_key(dev))
        if not zk.Connect_Net(dev.ip, dev.port): return JsonResponse({"error": "Gagal terhubung"}, status=500)
        
        zk.EnableDevice(1, False)
        success_count = 0
        for u in updates:
            if zk.SSR_SetUserInfo(1, str(u.get("pin")), str(u.get("nama", ""))[:24], "", int(u.get("privilege", 0)), bool(u.get("enabled", True))):
                success_count += 1
                
        zk.RefreshData(1)
        users = _fetch_users_direct(zk)
        zk.EnableDevice(1, True)
        zk.Disconnect()
        
        record_log(request, f"Import/Update massal {success_count} nama karyawan di mesin {dev.ip}")
        return JsonResponse({"message": f"{success_count} user diperbarui.", "users": users})
    except Exception as e: return JsonResponse({"error": str(e)}, status=500)
    finally: pythoncom.CoUninitialize()

# @csrf_exempt
def batch_delete_users(request, dev_id):
    if request.method != 'POST': return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        dev = Device.objects.get(id=dev_id)
        data = json.loads(request.body)
        pins_to_delete = data.get('pins', [])
    except: return JsonResponse({"error": "Error."}, status=400)

    if not pins_to_delete: return JsonResponse({"error": "Kosong."}, status=400)

    pythoncom.CoInitialize() 
    try:
        zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
        zk.SetCommPassword(_get_comm_key(dev))
        if not zk.Connect_Net(dev.ip, dev.port): return JsonResponse({"error": "Gagal konek"}, status=500)
            
        zk.EnableDevice(1, False)
        berhasil = 0
        for pin in pins_to_delete:
            zk.SSR_SetUserInfo(1, str(pin), "", "", 0, True)
            if zk.SSR_DeleteEnrollData(1, str(pin), 12):
                berhasil += 1
                
        zk.RefreshData(1)
        users = _fetch_users_direct(zk)
        zk.EnableDevice(1, True)
        zk.Disconnect()

        record_log(request, f"Menghapus massal {berhasil} karyawan dari mesin {dev.ip}")
        return JsonResponse({'message': f'Hapus {berhasil} user.', 'users': users})
    except Exception as e: return JsonResponse({'error': str(e)}, status=500)
    finally: pythoncom.CoUninitialize() 


# --- HELPER ZKTECO ---
def _fetch_users_direct(zk):
    users = []
    if zk.ReadAllUserID(1):
        sEnrollNumber, sName, sPassword, iPrivilege, bEnabled = "", "", "", 0, True
        while True:
            stat, sEnrollNumber, sName, sPassword, iPrivilege, bEnabled = zk.SSR_GetAllUserInfo(1, sEnrollNumber, sName, sPassword, iPrivilege, bEnabled)
            if not stat: break
            users.append({
                "user_id": clean_string(sEnrollNumber).strip(),
                "nama": clean_string(sName).strip(),
                "role": "Admin" if iPrivilege != 0 else "User",
                "kode_privilege": iPrivilege,
                "enabled": bEnabled
            })
    return users

def _get_users_from_machine(dev):
    pythoncom.CoInitialize()
    try:
        zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
        zk.SetCommPassword(_get_comm_key(dev))
        if not zk.Connect_Net(dev.ip, dev.port):
            return [], "Gagal terhubung."
        zk.EnableDevice(1, False)
        data = _fetch_users_direct(zk)
        zk.EnableDevice(1, True)
        zk.Disconnect()
        return data, None
    except Exception as e: return [], str(e)
    finally: pythoncom.CoUninitialize()

# ==========================================
# 5. TOOLS EXCEL
# ==========================================
def download_excel_template(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template Import"
    ws.append(["user_id", "nama"])
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E7652", end_color="1E7652", fill_type="solid")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.append(["1001", "Contoh Nama"])
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 36

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = 'attachment; filename="Template_Import_Karyawan.xlsx"'
    return response

def export_users_excel(request, dev_id):
    try: dev = Device.objects.get(id=dev_id)
    except: return JsonResponse({"error": "Not found"}, status=404)
    
    raw_users, err = _get_users_from_machine(dev)
    if err: return JsonResponse({"error": err}, status=502)

    record_log(request, f"Mengekspor data karyawan (Excel) dari mesin {dev.ip}")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["user_id", "nama", "role", "status"])
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E7652", end_color="1E7652", fill_type="solid")
    for cell in ws[1]: cell.font, cell.fill, cell.alignment = header_font, header_fill, Alignment(horizontal="center", vertical="center")

    for u in raw_users:
        ws.append([str(u.get("user_id", "")), str(u.get("nama", "")), str(u.get("role", "User")), "Aktif" if u.get("enabled", True) else "Nonaktif"])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"Data_User_{dev.ip}.xlsx"
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

# @csrf_exempt
def preview_excel(request, dev_id):
    if request.method != 'POST': return JsonResponse({"error": "Method not allowed"}, status=405)
    try: dev = Device.objects.get(id=dev_id)
    except: return JsonResponse({"error": "Not found"}, status=404)
    
    uploaded_file = request.FILES.get("file")
    if not uploaded_file: return JsonResponse({"error": "File Excel wajib diunggah."}, status=400)
    
    try:
        wb = openpyxl.load_workbook(uploaded_file, data_only=True)
        ws = wb.active
    except Exception as exc: return JsonResponse({"error": f"Gagal membaca file: {exc}"}, status=400)

    current_users, err = _get_users_from_machine(dev)
    if err: return JsonResponse({"error": err}, status=502)

    rows = list(ws.iter_rows(values_only=True))
    if not rows: return JsonResponse({"error": "File Excel kosong."}, status=400)
    header_row = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
    id_col_idx, name_col_idx = 0, 1

    for idx, col_name in enumerate(header_row):
        if any(a in col_name for a in ["id", "pin", "user_id"]): id_col_idx = idx
        elif any(a in col_name for a in ["nama", "name"]): name_col_idx = idx

    preview_list, seen_pins = [], set()
    for r in rows[1:]:
        if not r or len(r) <= max(id_col_idx, name_col_idx): continue
        if r[id_col_idx] is None or r[name_col_idx] is None: continue

        pin_str = str(r[id_col_idx]).strip().replace(".0", "")
        new_name_str = str(r[name_col_idx]).strip()
        if not pin_str or pin_str in seen_pins: continue

        seen_pins.add(pin_str)
        existing = next((u for u in current_users if str(u.get("user_id", "")) == pin_str), None)

        if existing:
            old_name = str(existing.get("nama", "")).strip()
            is_changed = old_name != new_name_str
            preview_list.append({
                "pin": pin_str, "current_name": old_name or "—", "new_name": new_name_str,
                "role": existing.get("role", "User"), "privilege": int(existing.get("kode_privilege", 0)),
                "enabled": bool(existing.get("enabled", True)), "status": "changed" if is_changed else "unchanged"
            })
        else:
            preview_list.append({"pin": pin_str, "current_name": "—", "new_name": new_name_str, "role": "—", "privilege": 0, "enabled": True, "status": "not_found"})

    return JsonResponse({
        "summary": {
            "total_rows": len(preview_list),
            "changed_count": sum(1 for i in preview_list if i["status"] == "changed"),
            "unchanged_count": sum(1 for i in preview_list if i["status"] == "unchanged"),
            "not_found_count": sum(1 for i in preview_list if i["status"] == "not_found")
        },
        "preview": preview_list
    })