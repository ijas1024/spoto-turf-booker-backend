# turf/admin.py
from django.contrib import admin
from .models import (
    User, Turf, Booking, TurfSlot, DynamicPricing, TeamShuffler, Payment, Feedback, ContactMessage
)
from django.contrib.auth.admin import UserAdmin


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'phone_number')

    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Personal Info', {'fields': ('phone_number', 'profile_image', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'password1', 'password2',
                'phone_number', 'profile_image', 'role',
                'is_active', 'is_staff', 'is_superuser'
            ),
        }),
    )


# ✅ Register remaining models
admin.site.register(Turf)
admin.site.register(Booking)
admin.site.register(TurfSlot)
admin.site.register(TeamShuffler)
admin.site.register(Payment)
#admin.site.register(Feedback)


# ✅ FIXED: Correct admin for ContactMessage
@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'created_at')
    search_fields = ('name', 'email', 'message')
    readonly_fields = ('name', 'email', 'message', 'created_at')

    def has_add_permission(self, request):
        # prevent manual addition in admin (messages come from frontend)
        return False

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('turf', 'user', 'rating', 'comment', 'created_at')
    search_fields = ('turf__name', 'user__username', 'comment')
    list_filter = ('rating', 'turf')
