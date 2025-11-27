# your_app/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
import requests
from django.conf import settings

# 1. USER
class User(AbstractUser):
    ROLE_CHOICES = [
        ('player', 'Player'),
        ('owner', 'Owner'),
        ('admin', 'Admin'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='player')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.role})"

# 2. TURF
class Turf(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='turfs')
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=12, decimal_places=9, null=True, blank=True)
    longitude = models.DecimalField(max_digits=12, decimal_places=9, null=True, blank=True)
    price_per_hour = models.DecimalField(max_digits=8, decimal_places=2)
    amenities = models.TextField(help_text="Comma-separated list of amenities")
    image = models.ImageField(upload_to='turfs/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if (not self.latitude or not self.longitude) and self.address:
            try:
                api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", None)
                if api_key:
                    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={self.address}&key={api_key}"
                    resp = requests.get(url)
                    data = resp.json()
                    if data.get("status") == "OK":
                        loc = data["results"][0]["geometry"]["location"]
                        self.latitude = loc["lat"]
                        self.longitude = loc["lng"]
            except Exception as e:
                print("⚠️ Google Geocoding failed:", e)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

# 3. BOOKING
class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('confirm_after_payment', 'Confirm After Payment'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name='bookings')
    date = models.DateField()
    start_time = models.TimeField()
    duration_hours = models.PositiveIntegerField(default=1)
    end_time = models.TimeField(blank=True, null=True)
    slot = models.ForeignKey('TurfSlot', on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    total_price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default='pending')
    booking_status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # ✅ New field — store exact time owner approved booking
    approved_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        from datetime import datetime, timedelta, time
        if self.slot:
            self.start_time = self.slot.start_time
            delta = (
                datetime.combine(self.date, self.slot.end_time) -
                datetime.combine(self.date, self.slot.start_time)
            )
            hours = int(delta.total_seconds() // 3600)
            if hours <= 0:
                hours = 1
            self.duration_hours = hours

        start_dt = datetime.combine(self.date, self.start_time)
        self.end_time = (start_dt + timedelta(hours=self.duration_hours)).time()

        if self.turf:
            self.total_price = (self.turf.price_per_hour or 0) * self.duration_hours

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Booking #{self.id} - {self.user.username} - {self.turf.name}"


# 4. TIME SLOT (repeating daily)
class TurfSlot(models.Model):
    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name='slots')
    start_time = models.TimeField()
    end_time = models.TimeField()
    label = models.CharField(max_length=100, blank=True, null=True)  # optional e.g. "Evening slot"
    is_active = models.BooleanField(default=True)  # owner can disable a slot without deleting
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_time']
        unique_together = ('turf', 'start_time', 'end_time')

    def __str__(self):
        return f"{self.turf.name}: {self.start_time} - {self.end_time}"

# 5. TIME SLOT INSTANCE isn't necessary because bookings are per date (slot repeats daily)

# 6. DYNAMIC PRICING
class DynamicPricing(models.Model):
    turf = models.OneToOneField(Turf, on_delete=models.CASCADE, related_name='dynamic_pricing')
    base_price = models.DecimalField(max_digits=8, decimal_places=2)
    demand_factor = models.FloatField(default=1.0)
    weather_factor = models.FloatField(default=1.0)
    final_price = models.DecimalField(max_digits=8, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_final_price(self):
        self.final_price = self.base_price * self.demand_factor * self.weather_factor
        self.save()

    def __str__(self):
        return f"{self.turf.name} - ₹{self.final_price}"

# 7. TEAM SHUFFLER
class TeamShuffler(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='team_shufflers')
    name = models.CharField(max_length=100, blank=True, null=True)
    players = models.ManyToManyField(User, related_name='team_players')
    team_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name or 'Team Shuffle'} for Booking #{self.booking.id}"


# 8. PAYMENT
# in Payment model
class Payment(models.Model):
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    ]
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    transaction_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    payment_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    # ✅ new Razorpay fields
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Payment #{self.transaction_id} - {self.status}"

# 9. FEEDBACK
class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks')
    turf = models.ForeignKey(Turf, on_delete=models.CASCADE, related_name='feedbacks')
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.turf.name} ({self.rating}★)"

# 10. NOTIFICATION
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('booking_request', 'Booking Request'),
        ('booking_update', 'Booking Update'),
        ('system', 'System'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    message = models.CharField(max_length=255)
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, default='system')
    booking = models.ForeignKey('Booking', on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"To {self.recipient.username}: {self.message}"

# 11. CHAT MESSAGE
class ChatMessage(models.Model):
    booking = models.ForeignKey('Booking', on_delete=models.CASCADE, related_name='chat_messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Chat({self.booking.id}) {self.sender.username} → {self.receiver.username}: {self.message[:20]}"

# add this to turf/models.py (append after ChatMessage)
class GlobalChatMessage(models.Model):
    """
    Turf-wide chat where ANY user can message the turf owner (or owner can reply).
    This allows chatting before/after bookings.
    """
    turf = models.ForeignKey('Turf', on_delete=models.CASCADE, related_name='global_chat_messages')
    sender = models.ForeignKey('User', on_delete=models.CASCADE, related_name='global_sent_messages')
    # receiver optional - owner replies will specify a receiver_id to target a user
    receiver = models.ForeignKey('User', on_delete=models.CASCADE, related_name='global_received_messages', null=True, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"GlobalChat {self.turf_id} {self.sender.username}: {self.message[:30]}"
    

# 12. CONTACT MESSAGE
class ContactMessage(models.Model):
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='contact_messages')
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user_part = f" ({self.sender.username})" if self.sender else ""
        return f"Contact from {self.name}{user_part}"

