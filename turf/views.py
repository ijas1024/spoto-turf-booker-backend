# your_app/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from .models import Turf, User, Booking, TurfSlot, Notification
from .serializers import TurfSerializer, UserSignupSerializer, UserDetailSerializer, BookingSerializer, TurfSlotSerializer, NotificationSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import JsonResponse
from datetime import datetime, timedelta, time
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.db.models.expressions import RawSQL
import razorpay
import uuid
from django.utils.timezone import now
from django.conf import settings
from .models import Payment
from .models import ChatMessage
from .serializers import ChatMessageSerializer
from django.db import models


# NearbyTurf and TurfList — TurfList extended to include request in serializer context
class NearbyTurfView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        lati = request.data.get("lati")
        longi = request.data.get("longi")

        if not lati or not longi:
            return JsonResponse({"status": "error", "message": "Missing coordinates"}, status=400)

        try:
            latitude = float(lati)
            longitude = float(longi)
        except ValueError:
            return JsonResponse({"status": "error", "message": "Invalid coordinates"}, status=400)

        gcd_formula = (
            "6371 * acos(least(greatest("
            "cos(radians(%s)) * cos(radians(latitude)) * "
            "cos(radians(longitude) - radians(%s)) + "
            "sin(radians(%s)) * sin(radians(latitude)), -1), 1))"
        )

        results = []
        for t in Turf.objects.exclude(latitude__isnull=True, longitude__isnull=True):
            qs = Turf.objects.filter(id=t.id).annotate(
                distance=RawSQL(gcd_formula, (latitude, longitude, latitude))
            ).order_by("distance")

            dist = float(qs[0].distance)
            if dist <= 25:  # show within 25km
                results.append({
                    "id": t.id,
                    "name": t.name,
                    "location": t.location,
                    "address": t.address,
                    "latitude": t.latitude,
                    "longitude": t.longitude,
                    "price_per_hour": t.price_per_hour,
                    "image": request.build_absolute_uri(t.image.url) if t.image else None,
                    "distance_km": round(dist, 2),
                })

        results.sort(key=lambda e: e["distance_km"])
        return JsonResponse({"status": "ok", "data": results})


# List all turfs (no approval needed) — ensure serializer gets request so image building works
class TurfList(generics.ListAPIView):
    queryset = Turf.objects.all()
    serializer_class = TurfSerializer
    permission_classes = [AllowAny]

    def get_serializer_context(self):
        # include request so TurfSerializer.build_absolute_uri works
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


import threading
from django.core.mail import send_mail

class UserSignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserSignupSerializer(data=request.data)
        if serializer.is_valid():
            raw_password = request.data.get("password")
            user = serializer.save()

            # ✅ send credentials email asynchronously (non-blocking)
            subject = "Welcome to Turf Booking System!"
            message = (
                f"Hi {user.username},\n\n"
                f"Your {user.role} account has been created successfully.\n\n"
                f"Here are your login details:\n"
                f"Username: {user.username}\n"
                f"Password: {raw_password}\n\n"
                f"Please keep this email safe and do not share your password.\n\n"
                f"Thanks,\nTurf Booking Team"
            )
            recipient = user.email

            def send_async_email():
                try:
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=True)
                except Exception as e:
                    print("⚠️ Email sending failed (non-blocking):", e)

            threading.Thread(target=send_async_email).start()

            refresh = RefreshToken.for_user(user)
            return Response({
                "message": f"{user.role.capitalize()} account created successfully",
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "username": user.username,
                "role": user.role,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        user = authenticate(username=username, password=password)
        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "username": user.username,
                "role": user.role,
            })
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserDetailSerializer(request.user, context={'request': request})
        return Response(serializer.data)


class UpdateProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = UserDetailSerializer(request.user, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully"})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        serializer = UserDetailSerializer(request.user, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Profile updated successfully"})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AddTurfView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        if request.user.role != "owner":
            return Response(
                {"error": "Only owners can add turfs."},
                status=status.HTTP_403_FORBIDDEN
            )

        data = request.data.copy()

        # ✅ Fix amenities conversion
        amenities = data.get("amenities", "")
        if isinstance(amenities, list):
            data["amenities"] = ",".join(amenities)
        elif not isinstance(amenities, str):
            data["amenities"] = str(amenities)

        # ✅ Pass both data and files correctly to serializer
        serializer = TurfSerializer(
            data=data,
            context={"request": request}
        )

        if serializer.is_valid():
            turf = serializer.save(owner=request.user)
            return Response(
                {
                    "message": "Turf added successfully!",
                    "turf": TurfSerializer(turf, context={"request": request}).data,
                },
                status=status.HTTP_201_CREATED,
            )

        print("❌ AddTurf validation errors:", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OwnerTurfList(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "owner":
            return Response({"error": "Only owners can view this."}, status=status.HTTP_403_FORBIDDEN)

        turfs = Turf.objects.filter(owner=request.user)
        serializer = TurfSerializer(turfs, many=True, context={'request': request})
        return Response(serializer.data)


class UpdateTurfView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def put(self, request, turf_id):
        try:
            turf = Turf.objects.get(id=turf_id, owner=request.user)
        except Turf.DoesNotExist:
            return Response({"error": "Turf not found or unauthorized"}, status=status.HTTP_404_NOT_FOUND)

        serializer = TurfSerializer(turf, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Turf updated successfully", "turf": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TurfDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, turf_id):
        try:
            turf = Turf.objects.get(id=turf_id, owner=request.user)
            turf.delete()
            return Response({"message": "Turf deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
        except Turf.DoesNotExist:
            return Response({"error": "Turf not found or not yours"}, status=status.HTTP_404_NOT_FOUND)


# Owner slots (unchanged behavior)
class OwnerTurfSlotsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request, turf_id):
        try:
            turf = Turf.objects.get(id=turf_id, owner=request.user)
        except Turf.DoesNotExist:
            return Response({"error": "Turf not found or unauthorized"}, status=status.HTTP_404_NOT_FOUND)

        slots = turf.slots.all().order_by('start_time')
        serializer = TurfSlotSerializer(slots, many=True)
        return Response(serializer.data)

    def post(self, request, turf_id):
        try:
            turf = Turf.objects.get(id=turf_id, owner=request.user)
        except Turf.DoesNotExist:
            return Response({"error": "Turf not found or unauthorized"}, status=status.HTTP_404_NOT_FOUND)

        serializer = TurfSlotSerializer(data=request.data)
        if serializer.is_valid():
            slot = serializer.save(turf=turf)
            return Response(TurfSlotSerializer(slot).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OwnerTurfSlotDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, turf_id, slot_id):
        try:
            turf = Turf.objects.get(id=turf_id, owner=request.user)
            slot = turf.slots.get(id=slot_id)
        except (Turf.DoesNotExist, TurfSlot.DoesNotExist):
            return Response({"error": "Slot not found or unauthorized"}, status=status.HTTP_404_NOT_FOUND)
        today = timezone.localdate()
        future_bookings = slot.bookings.filter(date__gte=today).exclude(booking_status='cancelled')
        if future_bookings.exists():
            return Response({"error": "Slot has future bookings. Cancel bookings before deleting."}, status=status.HTTP_400_BAD_REQUEST)
        slot.delete()
        return Response({"message": "Slot deleted"}, status=status.HTTP_204_NO_CONTENT)


class TurfAvailableSlotsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, turf_id):
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({"error": "Please provide date as YYYY-MM-DD in ?date="}, status=status.HTTP_400_BAD_REQUEST)
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            turf = Turf.objects.get(id=turf_id)
        except Turf.DoesNotExist:
            return Response({"error": "Turf not found"}, status=status.HTTP_404_NOT_FOUND)

        slots = turf.slots.filter(is_active=True).order_by('start_time')
        result = []
        for s in slots:
            # only confirmed bookings block the slot from being selectable by others
            conflict = Booking.objects.filter(
                turf=turf,
                slot=s,
                date=date_obj,
                booking_status='confirmed'
            ).exists()

            result.append({
                "id": s.id,
                "label": f"{s.start_time} - {s.end_time}",
                "start_time": s.start_time,
                "end_time": s.end_time,
                "is_available": not conflict
            })
        return Response({"date": date_str, "turf_id": turf.id, "slots": result})


class BookingView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        data = request.data.copy()
        data['user'] = request.user.id

        slot_id = data.get('slot')
        turf_id = data.get('turf')

        if not turf_id:
            return Response({"error": "turf is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            turf = Turf.objects.get(id=turf_id)
        except Turf.DoesNotExist:
            return Response({"error": "Turf not found"}, status=status.HTTP_404_NOT_FOUND)

        if slot_id:
            try:
                slot = TurfSlot.objects.get(id=slot_id, turf=turf, is_active=True)
            except TurfSlot.DoesNotExist:
                return Response({"error": "Slot not found or not active"}, status=status.HTTP_404_NOT_FOUND)

            date_str = data.get('date')
            if not date_str:
                return Response({"error": "date is required when booking a slot"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

            # Prevent past-date bookings
            today = timezone.localdate()
            if date_obj < today:
                return Response({"error": "You cannot book past dates."}, status=status.HTTP_400_BAD_REQUEST)

            # Only CONFIRMED bookings block the slot (so pending requests do not block others)
            conflict = Booking.objects.filter(
                turf=turf,
                slot=slot,
                date=date_obj,
                booking_status='confirmed'
            ).exists()

            if conflict:
                return Response({"error": "Slot already booked for that date"}, status=status.HTTP_400_BAD_REQUEST)

            # create pending booking
            booking = Booking.objects.create(
                user=request.user,
                turf=turf,
                slot=slot,
                date=date_obj,
                booking_status='pending'
            )

            Notification.objects.create(
                recipient=turf.owner,
                sender=request.user,
                notification_type='booking_request',
                message=f"New booking request from {request.user.username} for {turf.name} on {date_obj} ({slot.start_time}-{slot.end_time})",
                booking=booking
            )

            return Response({"message": "Booking request sent for approval!", "booking": BookingSerializer(booking).data}, status=status.HTTP_201_CREATED)

        # fallback: start_time/duration based
        serializer = BookingSerializer(data=data)
        if serializer.is_valid():
            booking = serializer.save(user=request.user)
            Notification.objects.create(
                recipient=booking.turf.owner,
                sender=request.user,
                notification_type='booking_request',
                message=f"New booking request from {request.user.username} for {booking.turf.name} on {booking.date} {booking.start_time}-{booking.end_time}",
                booking=booking
            )
            return Response({"message": "Booking request sent for approval!", "booking": BookingSerializer(booking).data}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        bookings = Booking.objects.filter(user=request.user).order_by("-created_at")
        serializer = BookingSerializer(bookings, many=True, context={'request': request})
        return Response(serializer.data)
    

# 🔹 Create Razorpay order (advance payment = half)
class CreatePaymentOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request, booking_id):
        try:
            booking = Booking.objects.get(id=booking_id, user=request.user)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=404)

        if booking.booking_status not in ["confirmed", "confirm_after_payment"]:
            return Response({"error": "Only approved bookings can be paid for."}, status=400)


        advance_amount = float(booking.total_price) / 2

        # Razorpay client
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        order = client.order.create({
            "amount": int(advance_amount * 100),  # paise
            "currency": "INR",
            "payment_capture": 1
        })

        # Save payment object
        payment = Payment.objects.create(
            booking=booking,
            transaction_id=str(uuid.uuid4()),
            amount=advance_amount,
            payment_method="Razorpay",
            razorpay_order_id=order["id"],
            status="pending"
        )


        return Response({
            "order_id": order["id"],
            "amount": advance_amount,
            "key": settings.RAZORPAY_KEY_ID,
            "currency": "INR"
        })


class VerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request, booking_id):
        data = request.data
        try:
            booking = Booking.objects.get(id=booking_id, user=request.user)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=404)

        try:
            payment = booking.payment
        except Payment.DoesNotExist:
            return Response({"error": "Payment record missing"}, status=404)

        # verify signature
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        params_dict = {
            'razorpay_order_id': data.get('razorpay_order_id'),
            'razorpay_payment_id': data.get('razorpay_payment_id'),
            'razorpay_signature': data.get('razorpay_signature')
        }

        try:
            client.utility.verify_payment_signature(params_dict)
            payment.status = "success"
            payment.razorpay_payment_id = data.get('razorpay_payment_id')
            payment.razorpay_signature = data.get('razorpay_signature')
            payment.save()

            booking.payment_status = "paid"
            booking.booking_status = "confirmed"
            booking.save()

            return Response({"message": "Payment successful!"})
        except:
            payment.status = "failed"
            payment.save()
            booking.booking_status = "rejected"
            booking.save()
            return Response({"error": "Payment verification failed"}, status=400)



from django.utils import timezone
import threading, time

# -------------------- UPDATED BookingApprovalView --------------------
class BookingApprovalView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request, booking_id):
        action = request.data.get("action")
        try:
            booking = Booking.objects.select_related('turf').get(
                id=booking_id, turf__owner=request.user
            )
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found or unauthorized"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if booking.booking_status != "pending":
            return Response(
                {"error": "Booking already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ✅ APPROVE
        if action == "approve":
            conflict = Booking.objects.filter(
                turf=booking.turf,
                slot=booking.slot,
                date=booking.date,
                booking_status="confirmed"
            ).exclude(id=booking.id).exists()

            if conflict:
                booking.booking_status = "rejected"
                booking.save()
                Notification.objects.create(
                    recipient=booking.user,
                    sender=request.user,
                    notification_type="booking_update",
                    message="Requested slot already taken; booking rejected.",
                    booking=booking,
                )
                return Response({"message": "Booking automatically rejected (slot taken)."}, status=200)

            # ✅ Approve booking — timer starts *now*
            booking.booking_status = "confirm_after_payment"
            booking.payment_status = "pending"
            booking.approved_at = timezone.now()
            booking.save()

            # ✅ Notify via Notification + Email
            notif_msg = f"Your booking for {booking.turf.name} on {booking.date} was approved. Please pay advance within 5 minutes!"
            Notification.objects.create(
                recipient=booking.user,
                sender=request.user,
                notification_type="booking_update",
                message=notif_msg,
                booking=booking,
            )

            # Send email asynchronously
            def send_booking_email():
                try:
                    send_mail(
                        subject="Booking Approved",
                        message=f"Hi {booking.user.username},\n\n{notif_msg}\n\nTurf: {booking.turf.name}\nDate: {booking.date}\n\nThanks,\nTurf Booking Team",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[booking.user.email],
                        fail_silently=True,
                    )
                except Exception as e:
                    print("⚠️ Failed to send approval email:", e)

            threading.Thread(target=send_booking_email).start()

            # ✅ background thread to auto-reject after 5 mins
            def auto_reject_if_unpaid(bid):
                time.sleep(300)  # 5 minutes = 300 seconds
                try:
                    b = Booking.objects.get(id=bid)
                    if b.payment_status != "paid" and b.booking_status == "confirm_after_payment":
                        b.booking_status = "rejected"
                        b.save()
                        Notification.objects.create(
                            recipient=b.user,
                            sender=b.turf.owner,
                            notification_type="booking_update",
                            message=f"Booking for {b.turf.name} on {b.date} auto-rejected (payment not received in 5 mins).",
                            booking=b,
                        )

                        # Send email for auto rejection
                        send_mail(
                            subject="Booking Auto-Rejected",
                            message=f"Hi {b.user.username},\n\nYour booking for {b.turf.name} on {b.date} was automatically rejected because payment was not completed within 5 minutes.\n\nThanks,\nTurf Booking Team",
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[b.user.email],
                            fail_silently=True,
                        )
                except Booking.DoesNotExist:
                    pass

            threading.Thread(target=auto_reject_if_unpaid, args=(booking.id,)).start()

            return Response({"message": "Booking approved! Payment countdown started for 5 minutes."})

        # ✅ REJECT
        elif action == "reject":
            booking.booking_status = "rejected"
            booking.save()

            notif_msg = f"Your booking for {booking.turf.name} on {booking.date} was rejected."
            Notification.objects.create(
                recipient=booking.user,
                sender=request.user,
                notification_type="booking_update",
                message=notif_msg,
                booking=booking,
            )

            # Send rejection email
            def send_reject_email():
                try:
                    send_mail(
                        subject="Booking Rejected",
                        message=f"Hi {booking.user.username},\n\n{notif_msg}\n\nThanks,\nTurf Booking Team",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[booking.user.email],
                        fail_silently=True,
                    )
                except Exception as e:
                    print("⚠️ Failed to send rejection email:", e)

            threading.Thread(target=send_reject_email).start()

            return Response({"message": "Booking rejected successfully!"})

        return Response({"error": "Invalid action"}, status=400)




class OwnerBookingRequestsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        if request.user.role != "owner":
            return Response({"error": "Only owners can view this"}, status=status.HTTP_403_FORBIDDEN)
        pending_bookings = Booking.objects.filter(turf__owner=request.user, booking_status='pending').order_by('-created_at')
        serializer = BookingSerializer(pending_bookings, many=True, context={'request': request})
        return Response(serializer.data)
    
from django.db.models import Sum, Q
from django.utils.timezone import localdate


class OwnerBookingsSummaryView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        if request.user.role != "owner":
            return Response({"error": "Only owners can view this page"}, status=403)

        # Get filter parameter (?filter=today|yesterday|month)
        filter_param = request.query_params.get("filter", "today")
        today = localdate()

        if filter_param == "yesterday":
            start_date = today - timedelta(days=1)
            end_date = start_date
        elif filter_param == "month":
            start_date = today.replace(day=1)
            end_date = today
        else:  # default: today
            start_date = today
            end_date = today

        bookings = (
            Booking.objects.filter(
                turf__owner=request.user,
                booking_status="confirmed",
                payment_status="paid",
                date__range=[start_date, end_date],
            )
            .select_related("turf", "user")
            .order_by("-date")
        )

        serializer = BookingSerializer(bookings, many=True, context={"request": request})

        total_income = bookings.aggregate(total=Sum("total_price"))["total"] or 0.0

        return Response({
            "filter": filter_param,
            "total_income": total_income,
            "bookings": serializer.data,
        })


# ✅ TEAM SHUFFLER API
from .models import TeamShuffler
from rest_framework import status

class TeamShufflerView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request, booking_id):
        """Retrieve all saved team shuffles for a booking"""
        try:
            booking = Booking.objects.get(id=booking_id, user=request.user)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)

        shuffles = TeamShuffler.objects.filter(booking=booking).order_by('-created_at')

        if not shuffles.exists():
            return Response({"saved_shuffles": []}, status=status.HTTP_200_OK)

        result = []
        for ts in shuffles:
            result.append({
                "id": ts.id,
                "name": ts.name,
                "players": [p.username for p in ts.players.all()],
                "teams": ts.team_data,
                "created_at": ts.created_at,
            })

        return Response({"saved_shuffles": result}, status=status.HTTP_200_OK)

    def post(self, request, booking_id):
        """Save a new team shuffle for a booking"""
        try:
            booking = Booking.objects.get(id=booking_id, user=request.user)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        name = data.get("name", "Untitled Shuffle")
        players = data.get("players", [])
        teams = data.get("teams", {})

        if not players or not teams:
            return Response({"error": "Missing player/team data"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Create new shuffle (no overwrite)
        ts = TeamShuffler.objects.create(
            booking=booking,
            name=name,
            team_data=teams
        )

        # ✅ Link players (existing users)
        user_objs = User.objects.filter(username__in=players)
        ts.players.add(*user_objs)

        return Response({"message": "Teams saved successfully!"}, status=status.HTTP_201_CREATED)


class NotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
        serializer = NotificationSerializer(notifications, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({"message": "All notifications marked as read"})

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Turf, Booking, ChatMessage, GlobalChatMessage, User, Notification
from .serializers import ChatMessageSerializer, GlobalChatMessageSerializer

# 🔹 Private global chat — user ↔ owner per turf
class GlobalChatView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request, turf_id):
        turf = get_object_or_404(Turf, id=turf_id)
        user = request.user

        if user == turf.owner:
            qs = GlobalChatMessage.objects.filter(turf=turf).order_by('created_at')
        else:
            qs = GlobalChatMessage.objects.filter(
                turf=turf
            ).filter(Q(sender=user) | Q(receiver=user)).order_by('created_at')

        serializer = GlobalChatMessageSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, turf_id):
        turf = get_object_or_404(Turf, id=turf_id)
        user = request.user
        msg_text = (request.data.get('message') or '').strip()
        if not msg_text:
            return Response({'error': 'Message cannot be empty'}, status=400)

        if user == turf.owner:
            receiver_id = request.data.get('receiver_id')
            if not receiver_id:
                return Response({'error': 'receiver_id required for owner messages'}, status=400)
            receiver = get_object_or_404(User, id=receiver_id)
        else:
            receiver = turf.owner

        msg = GlobalChatMessage.objects.create(turf=turf, sender=user, receiver=receiver, message=msg_text)

        # Notify receiver
        try:
            Notification.objects.create(
                recipient=receiver,
                sender=user,
                notification_type='system',
                message=f'New message about {turf.name}'
            )
        except Exception:
            pass

        return Response(GlobalChatMessageSerializer(msg).data, status=201)


# 🔹 Owner chat conversation list
# ---------------- Owner Chat Conversation List ----------------
class OwnerConversationList(APIView):
    """
    Lists all users who have messaged any turf owned by the logged-in owner.
    Each conversation is grouped by turf and user.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can view this'}, status=403)

        from django.db.models import Q
        from .models import Turf, GlobalChatMessage

        conversations = []
        turfs = Turf.objects.filter(owner=request.user)

        for turf in turfs:
            # get all users who messaged this turf
            users = (
                GlobalChatMessage.objects.filter(turf=turf)
                .exclude(sender=request.user)
                .values('sender_id', 'sender__username')
                .distinct()
            )
            for u in users:
                conversations.append({
                    'turf_id': turf.id,
                    'turf_name': turf.name,
                    'user_id': u['sender_id'],
                    'username': u['sender__username'],
                })

        return Response(conversations)


# Booking chat already exists in your views as ChatView; ensure it is present and allows messages anytime.
# If you don't have it or want to replace, append this ChatView:

class ChatView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request, booking_id):
        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=404)

        if request.user not in [booking.user, booking.turf.owner]:
            return Response({'error': 'Not authorized'}, status=403)

        messages = ChatMessage.objects.filter(booking=booking).order_by('created_at')
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, booking_id):
        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=404)

        if request.user not in [booking.user, booking.turf.owner]:
            return Response({'error': 'Not authorized'}, status=403)

        message_text = (request.data.get('message') or '').strip()
        if not message_text:
            return Response({'error': 'Message cannot be empty'}, status=400)

        receiver = booking.turf.owner if request.user == booking.user else booking.user

        msg = ChatMessage.objects.create(
            booking=booking,
            sender=request.user,
            receiver=receiver,
            message=message_text
        )

        try:
            Notification.objects.create(recipient=receiver, sender=request.user, notification_type='system', message=f'New chat message regarding booking #{booking.id}')
        except Exception:
            pass

        serializer = ChatMessageSerializer(msg)
        return Response(serializer.data, status=201)


# ✅ CONTACT FORM API
from .models import ContactMessage
from .serializers import ContactMessageSerializer

class ContactMessageView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        name = request.data.get("name", "").strip()
        email = request.data.get("email", "").strip()
        message = request.data.get("message", "").strip()

        if not name or not email or not message:
            return Response({"error": "All fields are required."}, status=400)

        user = request.user if request.user.is_authenticated else None
        msg = ContactMessage.objects.create(sender=user, name=name, email=email, message=message)

        # ✅ Notify all admin users
        admins = User.objects.filter(role="admin")
        for admin in admins:
            Notification.objects.create(
                recipient=admin,
                sender=user,
                notification_type="system",
                message=f"📩 New contact message from {name}: {message[:50]}"
            )

        # ✅ Send emails (non-blocking)
        def send_emails():
            try:
                # Notify admins
                admin_emails = [a.email for a in admins if a.email]
                if admin_emails:
                    send_mail(
                        subject=f"New Contact Message from {name}",
                        message=f"Name: {name}\nEmail: {email}\n\nMessage:\n{message}",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=admin_emails,
                        fail_silently=True,
                    )

                # Send acknowledgment to sender
                send_mail(
                    subject="Thank you for contacting Turf Booking Kerala!",
                    message=(
                        f"Hi {name},\n\n"
                        f"Thank you for reaching out to Turf Booking Kerala.\n"
                        f"We’ve received your message and will get back to you shortly.\n\n"
                        f"Best Regards,\nTurf Booking Team"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=True,
                )
            except Exception as e:
                print("⚠️ Email sending failed:", e)

        threading.Thread(target=send_emails).start()

        return Response({"message": "Your message was sent successfully!"}, status=201)
    
# ================================
# ✅ FEEDBACK & RATING VIEW (Final Secure Logic)
# ================================
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from .models import Feedback, Booking
from .serializers import FeedbackSerializer

class FeedbackView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    authentication_classes = [JWTAuthentication]

    def get(self, request, turf_id):
        """✅ Public: anyone can see reviews"""
        feedbacks = Feedback.objects.filter(turf_id=turf_id).order_by('-created_at')
        serializer = FeedbackSerializer(feedbacks, many=True)
        return Response(serializer.data)

    def post(self, request, turf_id):
        """✅ Only users with PAID + CONFIRMED booking can post"""
        user = request.user
        if not user.is_authenticated:
            return Response({"error": "Login required to post review."}, status=401)

        rating = request.data.get("rating")
        comment = request.data.get("comment", "").strip()

        # Validate rating
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return Response({"error": "Rating must be a number between 1 and 5."}, status=400)

        if rating not in range(1, 6):
            return Response({"error": "Rating must be between 1 and 5."}, status=400)

        # ✅ User must have a confirmed & paid booking for this turf
        has_paid_booking = Booking.objects.filter(
            user=user,
            turf_id=turf_id,
            booking_status="confirmed",
            payment_status="paid"
        ).exists()

        if not has_paid_booking:
            return Response(
                {"error": "⭐ You can rate this turf only after payment and confirmation."},
                status=403
            )

        # ✅ Save or update feedback
        feedback, created = Feedback.objects.update_or_create(
            user=user,
            turf_id=turf_id,
            defaults={"rating": rating, "comment": comment},
        )

        msg = "Review submitted successfully!" if created else "Review updated successfully!"
        return Response({"message": msg}, status=201)


# ================================
# ✅ CAN USER REVIEW CHECK API
# ================================
class CanReviewView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request, turf_id):
        """Return whether this user can review (confirmed + paid)"""
        user = request.user
        can_review = Booking.objects.filter(
            user=user,
            turf_id=turf_id,
            booking_status="confirmed",
            payment_status="paid"
        ).exists()
        return Response({"can_review": can_review})

# ================================
# ✅ OWNER TURF REVIEWS VIEW
# ================================
from rest_framework.permissions import IsAuthenticated
from .models import Feedback, Turf
from .serializers import FeedbackSerializer

class OwnerFeedbackView(APIView):
    """
    Allows a turf owner to see all reviews on their turfs.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        if request.user.role != "owner":
            return Response({"error": "Only owners can view this page."}, status=403)

        # Get all turfs owned by this owner
        turfs = Turf.objects.filter(owner=request.user)
        if not turfs.exists():
            return Response({"message": "You don’t have any turfs yet."}, status=200)

        # Collect feedback grouped by turf
        data = []
        for turf in turfs:
            feedbacks = Feedback.objects.filter(turf=turf).order_by("-created_at")
            serializer = FeedbackSerializer(feedbacks, many=True)
            data.append({
                "turf_id": turf.id,
                "turf_name": turf.name,
                "reviews": serializer.data
            })

        return Response(data, status=200)
