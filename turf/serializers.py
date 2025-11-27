from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from django.core.validators import RegexValidator, EmailValidator
from .models import ChatMessage, ContactMessage, Feedback, Turf, User, Booking, TurfSlot, Notification

class TurfSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Turf
        fields = "__all__"
        extra_fields = ["image_url"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image:
            image_url = obj.image.url
            if request:
                return request.build_absolute_uri(image_url)
            return f"http://127.0.0.1:8000{image_url}"
        return None


class TurfSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurfSlot
        fields = ['id', 'turf', 'start_time', 'end_time', 'label', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at', 'turf']


class UserDetailSerializer(serializers.ModelSerializer):
    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "phone_number", "profile_image", "profile_image_url", "role"]
        read_only_fields = ["role", "username"]

    def get_profile_image_url(self, obj):
        request = self.context.get("request")
        if obj.profile_image:
            image_url = obj.profile_image.url
            if request:
                return request.build_absolute_uri(image_url)
            return f"http://127.0.0.1:8000{image_url}"
        return None


class UserSignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(validators=[EmailValidator()])
    phone_number = serializers.CharField(
        validators=[RegexValidator(r'^\d{10}$', message="Phone number must be exactly 10 digits.")]
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'phone_number', 'profile_image', 'password', 'role']

    def validate_username(self, value):
        if len(value) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters long.")
        return value

    def validate_password(self, value):
        import re
        pattern = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$')
        if not pattern.match(value):
            raise serializers.ValidationError(
                "Password must be at least 8 characters long and include uppercase, lowercase, and number."
            )
        return make_password(value)

    def create(self, validated_data):
        return super().create(validated_data)


class BookingSerializer(serializers.ModelSerializer):
    turf_name = serializers.CharField(source='turf.name', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    turf = TurfSerializer(read_only=True)
    user = UserDetailSerializer(read_only=True)
    booking_status_display = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'user', 'user_name', 'turf', 'turf_name', 'slot', 'date',
            'start_time', 'duration_hours', 'end_time', 'total_price',
            'payment_status', 'booking_status', 'booking_status_display',
            'created_at'
        ]
        read_only_fields = ['id', 'user', 'end_time', 'total_price', 'created_at']

    def get_booking_status_display(self, obj):
        if obj.booking_status == "confirm_after_payment":
            return "Confirm After Payment"
        elif obj.booking_status == "confirmed":
            return "Confirmed"
        elif obj.booking_status == "pending":
            return "Pending Approval"
        elif obj.booking_status == "rejected":
            return "Rejected"
        else:
            return obj.booking_status


class NotificationSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    recipient_name = serializers.CharField(source='recipient.username', read_only=True)
    booking_id = serializers.IntegerField(source='booking.id', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'message', 'notification_type', 'sender_name', 'recipient_name', 'booking_id', 'is_read', 'created_at']

from rest_framework import serializers
from .models import ChatMessage, GlobalChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    receiver_name = serializers.CharField(source='receiver.username', read_only=True)

    class Meta:
        model = ChatMessage
        fields = ['id', 'booking', 'sender', 'receiver', 'sender_name', 'receiver_name', 'message', 'created_at']
        read_only_fields = ['id', 'created_at', 'sender', 'receiver', 'booking']

class GlobalChatMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    receiver_name = serializers.CharField(source='receiver.username', read_only=True)
    turf_name = serializers.CharField(source='turf.name', read_only=True)

    class Meta:
        model = GlobalChatMessage
        fields = ['id', 'turf', 'turf_name', 'sender', 'receiver', 'sender_name', 'receiver_name', 'message', 'created_at']
        read_only_fields = ['id', 'created_at', 'sender', 'receiver', 'turf']


class ConversationSerializer(serializers.Serializer):
    turf_id = serializers.IntegerField()
    turf_name = serializers.CharField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()

class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = '__all__'


# serializers.py
class FeedbackSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Feedback
        fields = ['id', 'user_name', 'rating', 'comment', 'created_at']
