import pythoncom
import win32com.client
import json
import re
import io
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from datetime import timedelta

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils.timezone import now, localtime

from .models import Device, AdminLog

# ==========================================
# 1. SISTEM LOGGING OTOMATIS & PEMBERSIHAN
# ==========================================
def get_client_ip(request):
    """Mengambil IP klien. Mendukung reverse proxy maupun koneksi langsung."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def record_log(request, action_text):
    """Mencatat aktivitas admin dan menghapus log yang usianya lebih dari 30 hari."""
    if request.user.is_authenticated:
        ip = get_client_ip(request)
        # Gunakan localtime(now()) agar waktu penyimpanan log disesuaikan ke zona waktu Asia/Jakarta
        waktu_lokal = localtime(now())
        AdminLog.objects.create(user=request.user, ip_address=ip, action=action_text, timestamp=waktu_lokal)
        
        # Auto-delete log lama (> 30 hari)
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

@csrf_exempt
def api_login(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user = authenticate(request, username=data.get('username'), password=data.get('password'))
        if user is not None:
            login(request, user)
            return JsonResponse({'message': 'Login berhasil'})
        return JsonResponse({'error': 'Username atau password salah'}, status=401)
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def api_logout(request):
    logout(request)
    return JsonResponse({'message': 'Logout berhasil'})


# ==========================================
# 3. MANAJEMEN ADMIN & LOGS (CRUD)
# ==========================================
@csrf_exempt
def handle_admins(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
        
    if request.method == 'GET':
        admins = User.objects.values('id', 'username', 'first_name', 'date_joined', 'is_superuser')
        admin_list = []
        for a in admins:
            waktu_lokal = localtime(a['date_joined']) if a['date_joined'] else None
            admin_list.append({
                "id": a['id'],
                "username": a['username'],
                "first_name": a['first_name'],
                "is_superuser": a['is_superuser'],
                "date_joined": waktu_lokal.strftime("%Y-%m-%d %H:%M:%S") if waktu_lokal else "-"
            })
        return JsonResponse({'admins': admin_list})
        
    elif request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        nama_lengkap = data.get('nama_lengkap', '').strip()
        password = data.get('password', '')
        
        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username sudah digunakan'}, status=400)
            
        User.objects.create_user(username=username, password=password, first_name=nama_lengkap)
        record_log(request, f"Membuat akun admin baru: {username}")
        
        # PASTIKAN ADA KATA 'return' DI SINI:
        return JsonResponse({'message': 'Admin berhasil ditambahkan'})

@csrf_exempt
def modify_admin(request, admin_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
        
    try:
        admin = User.objects.get(id=admin_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Admin tidak ditemukan'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            new_username = data.get('username', '').strip()
            new_name = data.get('nama_lengkap', '').strip()
            new_password = data.get('password', '').strip()

            if not new_username:
                return JsonResponse({'error': 'Username tidak boleh kosong'}, status=400)

            # Cek jika username sudah dipakai admin lain
            if User.objects.filter(username=new_username).exclude(id=admin_id).exists():
                return JsonResponse({'error': 'Username sudah digunakan oleh akun lain'}, status=400)

            admin.username = new_username
            admin.first_name = new_name
            if new_password:
                admin.set_password(new_password)
            admin.save()

            record_log(request, f"Memperbarui data akun admin: {new_username}")
            return JsonResponse({'message': 'Data admin berhasil diperbarui'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    elif request.method == 'DELETE':
        if request.user.id == admin_id:
            return JsonResponse({'error': 'Tidak dapat menghapus akun Anda sendiri.'}, status=400)
            
        target_uname = admin.username
        admin.delete()
        record_log(request, f"Menghapus akun admin: {target_uname}")
        return JsonResponse({'message': 'Admin berhasil dihapus'})

    return JsonResponse({'error': 'Method not allowed'}, status=405)

# Alias delete_admin ke modify_admin agar kompatibel
delete_admin = modify_admin

@csrf_exempt
def get_logs(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
        
    if request.method == 'GET':
        logs = AdminLog.objects.select_related('user').order_by('-timestamp')[:300]
        data = []
        for l in logs:
            # Gunakan localtime() agar otomatis mengkonversi UTC ke GMT+7 (Asia/Jakarta)
            waktu_lokal = localtime(l.timestamp) if l.timestamp else None
            
            data.append({
                "username": l.user.username if l.user else "Sistem",
                "ip": l.ip_address or "Local",
                "action": l.action,
                "waktu": waktu_lokal.strftime("%Y-%m-%d %H:%M:%S") if waktu_lokal else "-"
            })
        return JsonResponse({'logs': data})


# ==========================================
# 4. KONEKSI MESIN (ZKTECO) & USER DATA
# ==========================================
def _get_comm_key(dev):
    try:
        return int(dev.comm_key) if dev.comm_key is not None else 0
    except (ValueError, TypeError):
        return 0

def clean_string(val):
    if not isinstance(val, str): return str(val)
    return re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F-\x9F]', '', val)

def _fetch_users_direct(zk):
    """Fungsi pembantu internal untuk membaca daftar user langsung dari koneksi ZK yang aktif"""
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
    """Membuka koneksi baru ke mesin, menarik data user, lalu menutup koneksi"""
    pythoncom.CoInitialize()
    try:
        zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
        zk.SetCommPassword(_get_comm_key(dev))
        if not zk.Connect_Net(dev.ip, dev.port):
            return [], "Gagal terhubung ke mesin. Periksa IP, Port, atau pastikan Comm Key sudah benar."
        
        zk.EnableDevice(1, False)
        data = _fetch_users_direct(zk)
        zk.EnableDevice(1, True)
        zk.Disconnect()
        return data, None
    except Exception as e:
        return [], str(e)
    finally:
        pythoncom.CoUninitialize()

@csrf_exempt
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

        # Test koneksi sebelum disimpan
        pythoncom.CoInitialize()
        try:
            zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
            zk.SetCommPassword(comm_key)
            if not zk.Connect_Net(ip, port):
                return JsonResponse({"error": "Gagal terhubung ke mesin. Periksa IP, Port, dan Comm Key."}, status=400)
            
            zk.EnableDevice(1, False)
            users = _fetch_users_direct(zk)
            zk.EnableDevice(1, True)
            zk.Disconnect()
        except Exception as e:
            return JsonResponse({"error": f"Error koneksi mesin: {str(e)}"}, status=500)
        finally:
            pythoncom.CoUninitialize()

        # Jika sukses terhubung, baru simpan ke DB
        device = Device.objects.create(name=nama_mesin, ip=ip, port=port, comm_key=comm_key)
        record_log(request, f"Mendaftarkan mesin baru: {nama_mesin or ip}")
        return JsonResponse({"device": device.to_dict(), "users": users})

@csrf_exempt
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
                try:
                    dev.comm_key = int(raw_key) if raw_key != "" else 0
                except:
                    dev.comm_key = 0
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

@csrf_exempt
def connect_device(request, dev_id):
    if request.method == 'POST':
        try:
            dev = Device.objects.get(id=dev_id)
            users, err = _get_users_from_machine(dev)
            if err:
                return JsonResponse({"error": err}, status=400)
            record_log(request, f"Terhubung dengan mesin {dev.ip}")
            return JsonResponse({"device": dev.to_dict(), "users": users})
        except Device.DoesNotExist:
            return JsonResponse({"error": "Mesin tidak ditemukan"}, status=404)

@csrf_exempt
def handle_users(request, dev_id):
    if request.method == 'GET':
        try:
            dev = Device.objects.get(id=dev_id)
            users, err = _get_users_from_machine(dev)
            if err:
                return JsonResponse({"error": err}, status=400)
            record_log(request, f"Mensinkronkan (Refresh) data karyawan dari mesin {dev.ip}")
            return JsonResponse({"users": users})
        except Device.DoesNotExist:
            return JsonResponse({"error": "Mesin tidak ditemukan"}, status=404)

@csrf_exempt
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
                    record_log(request, f"Mengedit detail karyawan ID {pin} (Nama: {nama}) di mesin {dev.ip}")
                    return JsonResponse({"message": "User diperbarui", "users": users})
                else:
                    return JsonResponse({"error": "Gagal menyimpan ke mesin. Coba persingkat nama."}, status=500)
            
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
                record_log(request, f"Menghapus karyawan ID {pin} secara permanen dari mesin {dev.ip}")
                return JsonResponse({"message": "User dihapus", "users": users})
            return JsonResponse({"error": "Gagal menghapus data dari mesin"}, status=500)

    finally:
        pythoncom.CoUninitialize()


@csrf_exempt
def batch_update_users(request, dev_id):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        dev = Device.objects.get(id=dev_id)
        data = json.loads(request.body)
        updates = data.get("updates", [])
    except Exception:
        return JsonResponse({"error": "Format JSON tidak valid."}, status=400)
    
    if not updates:
        return JsonResponse({"error": "Tidak ada data untuk diperbarui."}, status=400)

    pythoncom.CoInitialize()
    try:
        zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
        zk.SetCommPassword(_get_comm_key(dev))
        
        if not zk.Connect_Net(dev.ip, dev.port):
            return JsonResponse({"error": "Gagal terhubung ke mesin"}, status=500)
        
        zk.EnableDevice(1, False)
        success_count = 0

        for u in updates:
            pin = str(u.get("pin"))
            nama = str(u.get("nama", ""))[:24]
            privilege = int(u.get("privilege", 0))
            enabled = bool(u.get("enabled", True))
            
            if zk.SSR_SetUserInfo(1, pin, nama, "", privilege, enabled):
                success_count += 1
                
        zk.RefreshData(1)
        users = _fetch_users_direct(zk)
        zk.EnableDevice(1, True)
        zk.Disconnect()
        
        record_log(request, f"Memperbarui massal (import excel) nama {success_count} karyawan di mesin {dev.ip}")
        return JsonResponse({
            "message": f"{success_count} dari {len(updates)} user berhasil diperbarui.",
            "users": users
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        pythoncom.CoUninitialize()

@csrf_exempt
def batch_delete_users(request, dev_id):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
        
    try:
        dev = Device.objects.get(id=dev_id)
        data = json.loads(request.body)
        pins_to_delete = data.get('pins', [])
    except Exception:
        return JsonResponse({"error": "Terjadi kesalahan payload."}, status=400)

    if not pins_to_delete:
        return JsonResponse({"error": "Tidak ada user yang dipilih."}, status=400)

    pythoncom.CoInitialize() 
    try:
        zk = win32com.client.Dispatch("zkemkeeper.ZKEM")
        zk.SetCommPassword(_get_comm_key(dev))
        
        if not zk.Connect_Net(dev.ip, dev.port):
            return JsonResponse({"error": "Gagal terhubung ke mesin"}, status=500)
            
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
        return JsonResponse({
            'message': f'Berhasil menghapus {berhasil} user.',
            'users': users
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    finally:
        pythoncom.CoUninitialize() 


# ==========================================
# 5. TOOLS EXCEL
# ==========================================
def download_excel_template(request):
    """Menghasilkan file Excel template kosong untuk digunakan sebagai template import."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template Import"

    headers = ["user_id", "nama"]
    ws.append(headers)

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E7652", end_color="1E7652", fill_type="solid")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.append(["1001", "Contoh Nama Karyawan 1"])
    ws.append(["1002", "Contoh Nama Karyawan 2"])
    ws.append(["1003", "Contoh Nama Karyawan 3"])

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 36

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = 'attachment; filename="Template_Import_Karyawan.xlsx"'
    return response

def export_users_excel(request, dev_id):
    try:
        dev = Device.objects.get(id=dev_id)
    except Device.DoesNotExist:
        return JsonResponse({"error": "Mesin tidak ditemukan."}, status=404)
    
    raw_users, err = _get_users_from_machine(dev)
    if err:
        return JsonResponse({"error": err}, status=502)

    record_log(request, f"Mengekspor daftar karyawan ke format Excel dari mesin {dev.ip}")

    # Ratakan struktur data
    users = []
    if isinstance(raw_users, dict): users.append(raw_users)
    elif isinstance(raw_users, (list, tuple)):
        for item in raw_users:
            if isinstance(item, dict): users.append(item)
            elif isinstance(item, (list, tuple)):
                for subitem in item:
                    if isinstance(subitem, dict): users.append(subitem)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data Karyawan"

    headers = ["user_id", "nama", "role", "status"]
    ws.append(headers)

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E7652", end_color="1E7652", fill_type="solid")
    for cell in ws[1]:
        cell.font, cell.fill, cell.alignment = header_font, header_fill, Alignment(horizontal="center", vertical="center")

    for u in users:
        ws.append([
            str(u.get("user_id") or u.get("id_mesin", "")),
            str(u.get("nama", "")),
            str(u.get("role", "User")),
            "Aktif" if u.get("enabled", True) else "Nonaktif"
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    clean_name = re.sub(r'[^\w\-_\. ]', '_', dev.name or f"Mesin_{dev.id}").strip().replace(' ', '_')
    filename = f"Data_User_{clean_name}.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@csrf_exempt
def preview_excel(request, dev_id):
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        dev = Device.objects.get(id=dev_id)
    except Device.DoesNotExist:
        return JsonResponse({"error": "Mesin tidak ditemukan."}, status=404)
        
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"error": "File Excel wajib diunggah."}, status=400)

    try:
        wb = openpyxl.load_workbook(uploaded_file, data_only=True)
        ws = wb.active
    except Exception as exc:
        return JsonResponse({"error": f"Gagal membaca file Excel: {exc}"}, status=400)

    raw_users, err = _get_users_from_machine(dev)
    if err: return JsonResponse({"error": err}, status=502)

    current_users = []
    if isinstance(raw_users, dict): current_users.append(raw_users)
    elif isinstance(raw_users, (list, tuple)):
        for item in raw_users:
            if isinstance(item, dict): current_users.append(item)
            elif isinstance(item, (list, tuple)):
                for subitem in item:
                    if isinstance(subitem, dict): current_users.append(subitem)

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return JsonResponse({"error": "File Excel kosong."}, status=400)

    header_row = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
    id_col_idx = None
    name_col_idx = None

    id_aliases = ["id_mesin", "pin", "id", "user_id", "userid", "no", "nomor"]
    name_aliases = ["nama", "nama_karyawan", "name", "employee_name", "nama_lengkap", "pegawai"]

    for idx, col_name in enumerate(header_row):
        if id_col_idx is None and any(col_name == alias or alias in col_name for alias in id_aliases):
            id_col_idx = idx
        elif name_col_idx is None and any(col_name == alias or alias in col_name for alias in name_aliases):
            name_col_idx = idx

    start_row_idx = 1
    if id_col_idx is None or name_col_idx is None:
        id_col_idx, name_col_idx = 0, 1
        val0 = str(rows[0][0]).strip() if len(rows[0]) > 0 and rows[0][0] is not None else ""
        if val0.isdigit(): start_row_idx = 0

    preview_list = []
    seen_pins = set()

    for r in rows[start_row_idx:]:
        if not r or len(r) <= max(id_col_idx, name_col_idx): continue
        if r[id_col_idx] is None or r[name_col_idx] is None: continue

        pin_str = str(r[id_col_idx]).strip().replace(".0", "")
        new_name_str = str(r[name_col_idx]).strip()
        if not pin_str or pin_str in seen_pins: continue

        seen_pins.add(pin_str)
        existing = next((u for u in current_users if str(u.get("user_id", "")) == pin_str or str(u.get("id_mesin", "")) == pin_str), None)

        if existing:
            old_name = str(existing.get("nama", "")).strip()
            is_changed = old_name != new_name_str
            preview_list.append({
                "pin": pin_str,
                "current_name": old_name or "—",
                "new_name": new_name_str,
                "role": existing.get("role", "User"),
                "privilege": int(existing.get("kode_privilege", 0)),
                "enabled": bool(existing.get("enabled", True)),
                "status": "changed" if is_changed else "unchanged"
            })
        else:
            preview_list.append({
                "pin": pin_str, "current_name": "—", "new_name": new_name_str,
                "role": "—", "privilege": 0, "enabled": True, "status": "not_found"
            })

    return JsonResponse({
        "summary": {
            "total_rows": len(preview_list),
            "changed_count": sum(1 for item in preview_list if item["status"] == "changed"),
            "unchanged_count": sum(1 for item in preview_list if item["status"] == "unchanged"),
            "not_found_count": sum(1 for item in preview_list if item["status"] == "not_found")
        },
        "preview": preview_list
    })