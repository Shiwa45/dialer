from django.contrib.admin import AdminSite
from django.apps import apps

class CustomAdminSite(AdminSite):
    def get_app_list(self, request):
        app_list = super().get_app_list(request)
        # Ensure 'users' app is included in the app list
        users_app = None
        for app in app_list:
            if app['app_label'] == 'users':
                users_app = app
                break
        if not users_app:
            try:
                users_app_config = apps.get_app_config('users')
                users_app = {
                    'name': users_app_config.verbose_name,
                    'app_label': 'users',
                    'app_url': None,
                    'has_module_perms': True,
                    'models': [],
                }
                app_list.append(users_app)
            except LookupError:
                pass
        return app_list

custom_admin_site = CustomAdminSite(name='custom_admin')
