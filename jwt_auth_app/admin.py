from django.contrib import admin
from django.contrib.auth.models import User

# Register your models here.

class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'is_active', 'is_staff', 'date_joined')
    search_fields = ('username', 'email')
    list_filter = ('is_active', 'is_staff', 'date_joined')


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
