from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    
    # Auth & Admin Management
    path('api/auth/login', views.api_login, name='api_login'),
    path('api/auth/logout', views.api_logout, name='api_logout'),
    path('api/admins', views.handle_admins, name='handle_admins'),
    path('api/admins/<int:admin_id>', views.modify_admin, name='modify_admin'),
    path('api/logs', views.get_logs, name='get_logs'),

    # Mesin & User
    path('api/devices', views.handle_devices, name='devices'),
    path('api/devices/<int:dev_id>', views.device_detail, name='device_detail'),
    path('api/devices/<int:dev_id>/connect', views.connect_device, name='connect_device'),
    path('api/devices/<int:dev_id>/users', views.handle_users, name='get_users'),
    
    # Tools Excel
    path('api/download-template', views.download_excel_template, name='download_template'),
    path('api/devices/<int:dev_id>/export-excel', views.export_users_excel, name='export_excel'),
    path('api/devices/<int:dev_id>/preview-excel', views.preview_excel, name='preview_excel'),
    path('api/devices/<int:dev_id>/users/batch', views.batch_update_users, name='batch_update'),
    path('api/devices/<int:dev_id>/users/batch-delete', views.batch_delete_users, name='batch_delete_users'),
    path('api/devices/<int:dev_id>/users/<str:pin>', views.modify_user, name='modify_user'),
]