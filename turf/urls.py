# your_app/urls.py
from django.urls import path
from .views import (
    BookingView, CanReviewView, ChatView, ContactMessageView, FeedbackView, GlobalChatView, NearbyTurfView, OwnerBookingsSummaryView, OwnerConversationList, OwnerFeedbackView, TeamShufflerView, TurfList, UpdateProfileView, UpdateTurfView, UserSignupView, LoginView,
    UserDetailView, AddTurfView, OwnerTurfList, OwnerBookingRequestsView, BookingApprovalView, NotificationsView,
    OwnerTurfSlotsView, OwnerTurfSlotDeleteView, TurfAvailableSlotsView, TurfDeleteView,CreatePaymentOrderView, VerifyPaymentView
)

urlpatterns = [
    path("turfs/", TurfList.as_view(), name="turf-list"),
    path("signup/", UserSignupView.as_view(), name="user-signup"),
    path("login/", LoginView.as_view(), name="user-login"),
    path("me/", UserDetailView.as_view(), name="user-detail"),
    path("update-profile/", UpdateProfileView.as_view(), name="update-profile"),
    path("owner/add-turf/", AddTurfView.as_view(), name="add-turf"),
    path("owner/turfs/", OwnerTurfList.as_view(), name="owner-turfs"),
    path("owner/turfs/<int:turf_id>/update/", UpdateTurfView.as_view(), name="update-turf"),
    path("owner/turfs/<int:turf_id>/delete/", TurfDeleteView.as_view(), name="delete-turf"),
    path("turfs/nearby/", NearbyTurfView.as_view(), name="nearby-turfs"),

    # slots
    path("owner/turfs/<int:turf_id>/slots/", OwnerTurfSlotsView.as_view(), name="owner-turf-slots"),
    path("owner/turfs/<int:turf_id>/slots/<int:slot_id>/delete/", OwnerTurfSlotDeleteView.as_view(), name="owner-turf-slot-delete"),

    # available slots for user
    path("turfs/<int:turf_id>/available-slots/", TurfAvailableSlotsView.as_view(), name="turf-available-slots"),

    # bookings & owner endpoints
    path('bookings/', BookingView.as_view(), name='booking-list'),                       # user list + create
    path('owner/bookings/', OwnerBookingRequestsView.as_view(), name='owner-bookings'),  # owner pending requests

    # Booking approval/reject — add both plural and singular forms to match any frontend requests.
    path('bookings/<int:booking_id>/action/', BookingApprovalView.as_view(), name='booking-action-plural'),
    path('booking/<int:booking_id>/action/', BookingApprovalView.as_view(), name='booking-action-singular'),

    path('notifications/', NotificationsView.as_view(), name='notifications'),

    path('bookings/<int:booking_id>/create-payment/', CreatePaymentOrderView.as_view(), name='create-payment'),
    path('bookings/<int:booking_id>/verify-payment/', VerifyPaymentView.as_view(), name='verify-payment'),

    path("owner/bookings-summary/", OwnerBookingsSummaryView.as_view(), name="owner-bookings-summary"),
    path("bookings/<int:booking_id>/team-shuffler/", TeamShufflerView.as_view(), name="team-shuffler"),

    
    # add near the end of urlpatterns
    path("turfs/<int:turf_id>/chat/", GlobalChatView.as_view(), name="turf-global-chat"),
    # booking chat already exists as:
    path("bookings/<int:booking_id>/chat/", ChatView.as_view(), name="chat"),
    path('owner/chats/', OwnerConversationList.as_view(), name='owner-conversations'),

    path("contact/", ContactMessageView.as_view(), name="contact-message"),
    path("turfs/<int:turf_id>/feedback/", FeedbackView.as_view(), name="turf-feedback"),

    path("turfs/<int:turf_id>/can-review/", CanReviewView.as_view(), name="can-review"),
    path("owner/feedbacks/", OwnerFeedbackView.as_view(), name="owner-feedbacks"),

]
