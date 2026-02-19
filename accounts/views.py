# accounts/views.py
from datetime import timedelta
import json
import secrets
import string
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction, IntegrityError
from django.db.models import (
    CharField, Count, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
)
from django.db.models.functions import Coalesce, Concat
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from competitions.models import CoachApproval, Enrollment, KyorugiCompetition
from .models import (
    CoachClubRequest, PendingClub, PendingCoach, PendingEditProfile,
    PendingUserProfile, SMSVerification, TkdBoard, TkdClub, UserProfile
)
from .serializers import (
    ClubCoachInfoSerializer, ClubSerializer, ClubStudentSerializer,
    DashboardKyorugiCompetitionSerializer, PendingClubSerializer,
    PendingCoachSerializer, PendingEditProfileSerializer,
    PendingPlayerSerializer, PhoneSerializer, UserProfileSerializer,
    VerifyCodeSerializer, VerifyLoginCodeSerializer, PlayerDashboardSerializer,
    CoachClubRequestSerializer,
)

from .utils import send_verification_code

from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)
User = get_user_model()

# ---------- Constants / Helpers ----------

ELIGIBLE_ENROLL_STATUSES = ('paid', 'confirmed', 'accepted', 'completed')


def _normalize_digits(s: str) -> str:
    if s is None:
        return ""
    return str(s).strip().translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )


def _detect_role(user):
    prof = getattr(user, "profile", None)
    if prof:
        return (prof.role or "player").lower()
    if TkdClub.objects.filter(user=user).exists():
        return "club"
    if TkdBoard.objects.filter(user=user).exists():
        return "heyat"
    return "player"


def annotate_student_stats(qs):
    enr = Enrollment.objects.filter(
        player_id=OuterRef('pk'), status__in=ELIGIBLE_ENROLL_STATUSES
    )
    enr_subq = (
        enr.order_by()
           .values('player_id')
           .annotate(c=Count('competition_id', distinct=True))
           .values('c')[:1]
    )
    zero_int = Value(0, output_field=IntegerField())
    return qs.annotate(
        competitions_count=Coalesce(Subquery(enr_subq, output_field=IntegerField()), zero_int),
        gold_total=Coalesce(F('gold_medals'), zero_int)
                   + Coalesce(F('gold_medals_country'), zero_int)
                   + Coalesce(F('gold_medals_int'), zero_int),
        silver_total=Coalesce(F('silver_medals'), zero_int)
                     + Coalesce(F('silver_medals_country'), zero_int)
                     + Coalesce(F('silver_medals_int'), zero_int),
        bronze_total=Coalesce(F('bronze_medals'), zero_int)
                     + Coalesce(F('bronze_medals_country'), zero_int)
                     + Coalesce(F('bronze_medals_int'), zero_int),
    )



def generate_unique_sms_code(phone: str, length: int = 4, ttl_minutes: int = 3) -> str:
    now = timezone.now()

    # همه کدهای فعال ۳ دقیقه اخیر
    recent_codes = SMSVerification.objects.filter(
        created_at__gte=now - timedelta(minutes=ttl_minutes)
    ).values_list('code', flat=True)
    recent_set = set(recent_codes)

    for _ in range(20):
        # کد ۴ رقمی بدون صفر اول (۱۰۰۰ تا ۹۹۹۹)
        code = str(secrets.randbelow(9000) + 1000)
        if code not in recent_set:
            return code

    # اگر خیلی بعید، تو ۲۰ تلاش یکتا پیدا نشد
    return str(secrets.randbelow(9000) + 1000)




def cleanup_expired_sms(ttl_minutes: int = 3):
    """
    تمام رکوردهای SMSVerification که بیشتر از ttl_minutes دقیقه از ساخت‌شان گذشته
    را پاک می‌کند.
    """
    cutoff = timezone.now() - timedelta(minutes=ttl_minutes)
    SMSVerification.objects.filter(created_at__lt=cutoff).delete()

# ---------- SMS (Register) ----------

class SendCodeAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        cleanup_expired_sms()
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        role = request.data.get("role")

        # جلوگیری از تداخل با داده‌های موجود
        if role in ['player', 'coach']:
            if UserProfile.objects.filter(phone=phone).exists() or PendingUserProfile.objects.filter(phone=phone).exists():
                return Response({"phone": "این شماره قبلاً ثبت شده است."}, status=status.HTTP_400_BAD_REQUEST)
        elif role == 'club':
            if TkdClub.objects.filter(founder_phone=phone).exists() or PendingClub.objects.filter(founder_phone=phone).exists():
                return Response({"phone": "این شماره قبلاً ثبت شده است."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"error": "نقش نامعتبر است."}, status=status.HTTP_400_BAD_REQUEST)

        # Rate limit 3 دقیقه
        recent = SMSVerification.objects.filter(
            phone=phone, created_at__gte=timezone.now() - timedelta(minutes=3)
        ).first()
        if recent:
            remaining = 180 - int((timezone.now() - recent.created_at).total_seconds())
            return Response({"error": "کد قبلی هنوز معتبر است.", "retry_after": remaining}, status=429)

        code = generate_unique_sms_code(phone)
        SMSVerification.objects.create(phone=phone, code=code)
        send_verification_code(phone, code)


        return Response({"message": "کد تأیید ارسال شد."}, status=200)


class VerifyCodeAPIView(APIView):
    """تایید کد پیامکی برای ثبت‌نام"""
    permission_classes = [AllowAny]

    def post(self, request):
        # 🧹 تمیزکاری رکوردهای منقضی‌شده
        cleanup_expired_sms()

        serializer = VerifyCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]
        expire_time = timezone.now() - timedelta(minutes=3)

        try:
            record = SMSVerification.objects.get(phone=phone, code=code)
        except SMSVerification.DoesNotExist:
            SMSVerification.objects.filter(phone=phone).delete()
            return Response({"error": "کد وارد شده نادرست است."}, status=400)

        if record.created_at < expire_time:
            record.delete()
            return Response({"error": "کد منقضی شده است. لطفاً مجدداً دریافت کنید."}, status=400)

        record.delete()
        return Response({"message": "کد تأیید شد. ادامه دهید."}, status=200)


# ---------- Form Data helpers ----------

@api_view(['GET'])
def form_data_player_view(request):
    gender = request.GET.get('gender')

    heyats = list(TkdBoard.objects.values('id', 'name'))
    clubs = list(TkdClub.objects.values('id', 'club_name'))

    coaches_qs = UserProfile.objects.filter(is_coach=True)
    if gender:
        coaches_qs = coaches_qs.filter(gender=gender)

    coaches = [{"id": c.id, "full_name": f"{c.first_name} {c.last_name}"} for c in coaches_qs]

    BELT_CHOICES = [
        ('سفید', 'سفید'),
        ('زرد', 'زرد'), ('سبز', 'سبز'), ('آبی', 'آبی'), ('قرمز', 'قرمز'),
        *[(f'مشکی دان {i}', f'مشکی دان {i}') for i in range(1, 11)]
    ]

    return Response({
        "heyats": heyats,
        "clubs": clubs,
        "coaches": coaches,
        "belt_choices": BELT_CHOICES,
    })


@api_view(['GET'])
def coaches_by_club_gender(request):
    club_id = request.GET.get('club')
    gender = request.GET.get('gender')

    coaches_qs = UserProfile.objects.filter(is_coach=True)

    if club_id:
        coaches_qs = coaches_qs.filter(coaching_clubs__id=club_id)
    if gender:
        coaches_qs = coaches_qs.filter(gender=gender)

    coaches = [{"id": c.id, "full_name": f"{c.first_name} {c.last_name}"} for c in coaches_qs]
    return Response({"coaches": coaches})


@csrf_exempt
@api_view(['GET'])
def form_data_view(request):
    gender = request.GET.get('gender')
    heyats = list(TkdBoard.objects.values('id', 'name'))
    clubs = list(TkdClub.objects.values('id', 'club_name'))

    coaches_qs = UserProfile.objects.filter(is_coach=True)
    if gender:
        coaches_qs = coaches_qs.filter(gender=gender)

    coaches = [{"id": c.id, "full_name": f"{c.first_name} {c.last_name}"} for c in coaches_qs]
    return Response({"heyats": heyats, "clubs": clubs, "coaches": coaches})


def check_national_code(request):
    code = request.GET.get("code")
    if not code:
        return JsonResponse({"exists": False})

    exists = (
        UserProfile.objects.filter(national_code=code).exists() or
        PendingUserProfile.objects.filter(national_code=code).exists()
    )
    return JsonResponse({"exists": exists})


# ---------- Register Coach / Player / Club ----------

class RegisterCoachAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def post(self, request, format=None):
        try:
            data = request.data.copy()

            # refereeTypes: string -> dict
            referee_raw = data.get('refereeTypes')
            if referee_raw and isinstance(referee_raw, str):
                try:
                    data['refereeTypes'] = json.loads(referee_raw)
                except json.JSONDecodeError:
                    data['refereeTypes'] = {}
            else:
                data['refereeTypes'] = data.get('refereeTypes', {}) or {}

            # selectedClubs: پشتیبانی از selectedClubs[] و selectedClubs(JSON)
            clubs = []
            if hasattr(request.data, "getlist"):
                clubs = request.data.getlist('selectedClubs[]') or []
            if not clubs:
                clubs_raw = data.get('selectedClubs')
                if isinstance(clubs_raw, str):
                    try:
                        clubs = json.loads(clubs_raw)
                    except json.JSONDecodeError:
                        clubs = []
                elif isinstance(clubs_raw, (list, tuple)):
                    clubs = list(clubs_raw)

            clubs = [int(c) for c in clubs if str(c).isdigit()]
            data['selectedClubs'] = clubs

            # نگاشت درجه‌های مربیگری
            if data.get('coachGradeNational'):
                data['coach_level'] = data['coachGradeNational']
            if data.get('coachGradeIntl'):
                data['coach_level_International'] = data['coachGradeIntl']

            # استخراج داوری‌ها از refereeTypes
            rt = data.get('refereeTypes', {})
            def _sel(k): return bool(rt.get(k, {}).get('selected'))
            def _lvl(k): return (rt.get(k, {}) or {}).get('gradeNational') or None
            def _intl(k): return (rt.get(k, {}) or {}).get('gradeIntl') or None

            for field in ['kyorogi', 'poomseh', 'hanmadang']:
                data[field] = _sel(field)
                if data[field]:
                    data[f'{field}_level'] = _lvl(field)
                    data[f'{field}_level_International'] = _intl(field)

            # cast برای FKها
            if data.get('tkd_board') and str(data['tkd_board']).isdigit():
                data['tkd_board'] = int(data['tkd_board'])

            coach_id = data.get('coach')
            if coach_id and coach_id != "other":
                data['coach'] = int(coach_id) if str(coach_id).isdigit() else None
            else:
                data['coach'] = None

            # اعتبارسنجی و ذخیره
            serializer = PendingCoachSerializer(data=data, context={'request': request})
            if not serializer.is_valid():
                return Response({'status': 'error', 'errors': serializer.errors}, status=400)

            instance = serializer.save()

            # ست‌کردن M2M باشگاه‌ها
            if clubs:
                instance.coaching_clubs.set(clubs)
                club_names = list(
                    TkdClub.objects.filter(id__in=clubs).values_list('club_name', flat=True)
                )
                instance.club_names = club_names
                # club پیش‌فرض
                try:
                    instance.club = TkdClub.objects.get(id=clubs[0])
                except TkdClub.DoesNotExist:
                    pass

            # انتساب coach
            if coach_id and coach_id != "other" and str(coach_id).isdigit():
                try:
                    coach_obj = UserProfile.objects.get(id=int(coach_id))
                    if coach_obj.phone == instance.phone:
                        return Response({'status': 'error', 'message': 'مربی نمی‌تواند مربی خودش باشد.'}, status=400)
                    instance.coach = coach_obj
                    instance.coach_name = f"{coach_obj.first_name} {coach_obj.last_name}"
                except UserProfile.DoesNotExist:
                    return Response({'status': 'error', 'message': 'مربی انتخاب‌شده نامعتبر است'}, status=400)

            instance.tkd_board_name = instance.tkd_board.name if instance.tkd_board else ''
            instance.save()

            return Response(
                {'status': 'ok', 'message': 'اطلاعات شما با موفقیت ثبت و در انتظار تأیید هیئت استان می‌باشد.'},
                status=200
            )

        except Exception as e:
            logger.exception("register-coach crashed")
            return Response(
                {'status': 'error', 'message': 'Internal error', 'detail': str(e)},
                status=500
            )


@staff_member_required
def approve_pending_user(request, pk):
    pending = get_object_or_404(PendingUserProfile, pk=pk)

    if pending.national_code and UserProfile.objects.filter(national_code=pending.national_code).exists():
        messages.warning(request, "این کاربر قبلاً تأیید شده است.")
        return redirect(reverse("admin:accounts_userprofile_changelist"))

    username = (pending.phone or "").strip()
    raw_pass = _normalize_digits(pending.national_code)

    coach_instance = UserProfile.objects.filter(id=pending.coach_id).first() if pending.coach_id else None
    # ✅ جلوگیری از coach=self بعد از تایید
    if coach_instance and _normalize_digits(coach_instance.national_code) == _normalize_digits(pending.national_code):
        coach_instance = None

    is_coach = pending.role in ['coach', 'both']
    is_referee = pending.role in ['referee', 'both']

    with transaction.atomic():
        user_obj = User.objects.filter(username=username).first() or User(username=username)
        if raw_pass:
            user_obj.set_password(raw_pass)
        else:
            user_obj.set_unusable_password()
        user_obj.save()

        user = UserProfile.objects.create(
            first_name=pending.first_name, last_name=pending.last_name, father_name=pending.father_name,
            national_code=pending.national_code, birth_date=pending.birth_date, phone=pending.phone,
            gender=pending.gender, role=pending.role, province=pending.province, county=pending.county,
            city=pending.city, tkd_board=pending.tkd_board,
            tkd_board_name=pending.tkd_board.name if pending.tkd_board else '',
            address=pending.address, profile_image=pending.profile_image,
            belt_grade=pending.belt_grade, belt_certificate_number=pending.belt_certificate_number,
            belt_certificate_date=pending.belt_certificate_date,
            is_coach=is_coach, coach_level=pending.coach_level, coach_level_International=pending.coach_level_International,
            is_referee=is_referee, kyorogi=pending.kyorogi, kyorogi_level=pending.kyorogi_level,
            kyorogi_level_International=pending.kyorogi_level_International,
            poomseh=pending.poomseh, poomseh_level=pending.poomseh_level, poomseh_level_International=pending.poomseh_level_International,
            hanmadang=pending.hanmadang, hanmadang_level=pending.hanmadang_level, hanmadang_level_International=pending.hanmadang_level_International,
            confirm_info=pending.confirm_info, club_names=pending.club_names, coach_name=pending.coach_name,
            club=pending.club, coach=coach_instance, user=user_obj
        )

        if pending.coaching_clubs.exists():
            user.coaching_clubs.set(pending.coaching_clubs.all())

        pending.delete()

    messages.success(request, "کاربر تأیید شد. نام‌کاربری = موبایل، رمز = کد ملی.")
    return redirect(reverse("admin:accounts_userprofile_changelist"))


class RegisterPlayerAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def post(self, request, format=None):
        data = request.data.copy()

        club_id = data.get('club')
        if club_id and str(club_id).isdigit():
            data['club'] = int(club_id)

        coach_id = data.get('coach')
        if coach_id and coach_id != "other":
            try:
                cid = int(coach_id)
                # اگر کاربر با همین phone/national_code بعداً تایید شود، در approve هم کنترل می‌کنیم.
                data['coach'] = cid
            except ValueError:
                data['coach'] = None


        serializer = PendingPlayerSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            instance = serializer.save()

            if instance.tkd_board:
                instance.tkd_board_name = instance.tkd_board.name
            if instance.club:
                instance.club_names = [instance.club.club_name]
            if instance.coach:
                instance.coach_name = f"{instance.coach.first_name} {instance.coach.last_name}"

            instance.save()
            return Response({'status': 'ok', 'message': 'اطلاعات شما با موفقیت ثبت و در انتظار تأیید هیئت استان میباشد.'}, status=200)

        return Response({'status': 'error', 'errors': serializer.errors}, status=400)


class RegisterPendingClubAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data

        # گاردهای سریع (اختیاری چون داخل سریالایزر هم هست)
        lic = (data.get('license_number') or '').strip()
        fid = (data.get('federation_id') or '').strip()

        if lic and (TkdClub.objects.filter(license_number__iexact=lic).exists()
                    or PendingClub.objects.filter(license_number__iexact=lic).exists()):
            return Response({"status": "error", "errors": {"license_number": ["این شماره مجوز قبلاً ثبت شده است."]}}, status=400)

        if fid and (TkdClub.objects.filter(federation_id__iexact=fid).exists()
                    or PendingClub.objects.filter(federation_id__iexact=fid).exists()):
            return Response({"status": "error", "errors": {"federation_id": ["این Federation ID قبلاً ثبت شده است."]}}, status=400)

        serializer = PendingClubSerializer(data=data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=400)

        club_instance = serializer.save()
        if club_instance.tkd_board:
            club_instance.tkd_board_name = club_instance.tkd_board.name
            club_instance.save()

        return Response({"status": "ok", "message": "باشگاه ثبت شد و در انتظار تایید است."}, status=201)


@staff_member_required
@require_POST
def approve_pending_club(request, pk):
    pending = get_object_or_404(PendingClub, pk=pk)

    cname = (pending.club_name or "").strip()
    ccity = (pending.city or "").strip()

    # تکراری بودن در اصلی‌ها فقط با نام+شهر
    if cname and ccity and TkdClub.objects.filter(
        club_name__iexact=cname,
        city__iexact=ccity,
    ).exists():
        messages.warning(request, "باشگاهی با همین نام در همین شهر قبلاً تأیید شده است.")
        return redirect("admin:accounts_pendingclub_changelist")

    try:
        with transaction.atomic():
            user_obj, created = User.objects.get_or_create(username=pending.founder_phone)
            if created:
                if pending.founder_national_code and pending.founder_national_code.isdigit():
                    user_obj.set_password(pending.founder_national_code)
                else:
                    user_obj.set_unusable_password()
                user_obj.save()

            TkdClub.objects.create(
                club_name=cname,
                founder_name=pending.founder_name,
                founder_national_code=pending.founder_national_code,
                founder_phone=pending.founder_phone,
                club_type=pending.club_type,
                activity_description=pending.activity_description,
                province=pending.province,
                county=pending.county,
                city=ccity,
                tkd_board=pending.tkd_board,
                phone=pending.phone,
                address=pending.address,
                license_number=pending.license_number or "",
                federation_id=pending.federation_id or "",
                license_image=pending.license_image,
                confirm_info=pending.confirm_info,
                user=user_obj,
            )

            pending.delete()

    except IntegrityError:
        messages.error(request, "تداخل اطلاعات رخ داد.")
        return redirect("admin:accounts_pendingclub_changelist")
    except Exception as e:
        messages.error(request, f"خطای غیرمنتظره: {e}")
        return redirect("admin:accounts_pendingclub_changelist")

    messages.success(request, "باشگاه با موفقیت تأیید و منتقل شد.")
    return redirect("admin:accounts_tkdclub_changelist")


# ---------- Club & Coach dashboards ----------

class ClubStudentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            club = TkdClub.objects.get(user=user)
        except TkdClub.DoesNotExist:
            return Response({"detail": "باشگاه یافت نشد"}, status=404)

        students = UserProfile.objects.filter(club=club, role='player')

        coach = request.GET.get("coach")
        if coach and coach != "مربی":
            students = students.annotate(
                full_name=Concat('coach__first_name', Value(' '), 'coach__last_name', output_field=CharField())
            ).filter(full_name__icontains=coach)

        belt = request.GET.get("belt")
        if belt and belt != "درجه کمربند":
            students = students.filter(belt_grade=belt)

        birth_from = request.GET.get("birth_from")
        if birth_from:
            students = students.filter(birth_date__gte=birth_from)

        birth_to = request.GET.get("birth_to")
        if birth_to:
            students = students.filter(birth_date__lte=birth_to)

        search = request.GET.get("search")
        if search:
            students = students.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(national_code__icontains=search)
            )

        students = annotate_student_stats(students)
        serialized = ClubStudentSerializer(students, many=True)
        return Response(serialized.data)


class ClubCoachesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            club = TkdClub.objects.get(user=request.user)
        except TkdClub.DoesNotExist:
            return Response({"detail": "باشگاه یافت نشد."}, status=404)

        coaches = UserProfile.objects.filter(coaching_clubs=club, is_coach=True)
        data = [{"id": coach.id, "name": f"{coach.first_name} {coach.last_name}"} for coach in coaches]
        return Response(data)


class ClubAllCoachesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            club = TkdClub.objects.get(user=request.user)
        except TkdClub.DoesNotExist:
            return Response({"detail": "باشگاه یافت نشد."}, status=404)

        all_coaches = UserProfile.objects.filter(is_coach=True)
        pending_requests = CoachClubRequest.objects.filter(club=club, status='pending')
        pending_map = {(req.coach_id, req.request_type): True for req in pending_requests}

        serializer = ClubCoachInfoSerializer(all_coaches, many=True, context={"club": club, "pending_map": pending_map})
        sorted_data = sorted(serializer.data, key=lambda x: not x['is_active'])
        return Response(sorted_data)


def with_competitions_count(qs):
    subq = (
        Enrollment.objects
        .filter(player_id=OuterRef('pk'), status__in=ELIGIBLE_ENROLL_STATUSES)
        .values('player')
        .annotate(c=Count('id'))
        .values('c')[:1]
    )
    return qs.annotate(competitions_count=Subquery(subq, output_field=IntegerField()))


class DashboardCombinedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, role):
        user = request.user

        if role == 'club':
            try:
                club = TkdClub.objects.get(user=user)
                members = UserProfile.objects.filter(club=club)

                student_count = members.filter(role='player').count()
                coach_count = UserProfile.objects.filter(coaching_clubs=club, is_coach=True).count()

                medals = members.aggregate(
                    gold_medals=Sum('gold_medals', default=0),
                    silver_medals=Sum('silver_medals', default=0),
                    bronze_medals=Sum('bronze_medals', default=0),
                    gold_medals_country=Sum('gold_medals_country', default=0),
                    silver_medals_country=Sum('silver_medals_country', default=0),
                    bronze_medals_country=Sum('bronze_medals_country', default=0),
                    gold_medals_int=Sum('gold_medals_int', default=0),
                    silver_medals_int=Sum('silver_medals_int', default=0),
                    bronze_medals_int=Sum('bronze_medals_int', default=0),
                )

                rankings = members.aggregate(
                    ranking_competition=Sum('ranking_competition', default=0),
                    ranking_total=Sum('ranking_total', default=0),
                )

                return Response({
                    "role": "club",
                    "club_name": club.club_name,
                    "founder_name": club.founder_name,
                    "student_count": student_count,
                    "coach_count": coach_count,
                    "matches_participated": club.matches_participated,
                    "gold_medals": medals["gold_medals"] or 0,
                    "silver_medals": medals["silver_medals"] or 0,
                    "bronze_medals": medals["bronze_medals"] or 0,
                    "gold_medals_country": medals["gold_medals_country"] or 0,
                    "silver_medals_country": medals["silver_medals_country"] or 0,
                    "bronze_medals_country": medals["bronze_medals_country"] or 0,
                    "gold_medals_int": medals["gold_medals_int"] or 0,
                    "silver_medals_int": medals["silver_medals_int"] or 0,
                    "bronze_medals_int": medals["bronze_medals_int"] or 0,
                    "ranking_competition": rankings["ranking_competition"] or 0,
                    "ranking_total": rankings["ranking_total"] or 0,
                })
            except TkdClub.DoesNotExist:
                return Response({"detail": "پروفایل باشگاه یافت نشد."}, status=404)

        elif role == 'heyat':
            try:
                board = TkdBoard.objects.get(user=user)
                members = UserProfile.objects.filter(tkd_board=board)

                student_count = members.filter(role='player').count()
                coach_count = members.filter(is_coach=True).count()
                referee_count = members.filter(is_referee=True).count()
                club_count = TkdClub.objects.filter(tkd_board=board).count()

                medals = members.aggregate(
                    gold_medals=Sum('gold_medals', default=0),
                    silver_medals=Sum('silver_medals', default=0),
                    bronze_medals=Sum('bronze_medals', default=0),
                    gold_medals_country=Sum('gold_medals_country', default=0),
                    silver_medals_country=Sum('silver_medals_country', default=0),
                    bronze_medals_country=Sum('bronze_medals_country', default=0),
                    gold_medals_int=Sum('gold_medals_int', default=0),
                    silver_medals_int=Sum('silver_medals_int', default=0),
                    bronze_medals_int=Sum('bronze_medals_int', default=0),
                )

                return Response({
                    "role": "heyat",
                    "board_name": board.name,
                    "student_count": student_count,
                    "coach_count": coach_count,
                    "referee_count": referee_count,
                    "club_count": club_count,
                    "gold_medals": medals["gold_medals"] or 0,
                    "silver_medals": medals["silver_medals"] or 0,
                    "bronze_medals": medals["bronze_medals"] or 0,
                    "gold_medals_country": medals["gold_medals_country"] or 0,
                    "silver_medals_country": medals["silver_medals_country"] or 0,
                    "bronze_medals_country": medals["bronze_medals_country"] or 0,
                    "gold_medals_int": medals["gold_medals_int"] or 0,
                    "silver_medals_int": medals["silver_medals_int"] or 0,
                    "bronze_medals_int": medals["bronze_medals_int"] or 0,
                })
            except TkdBoard.DoesNotExist:
                return Response({"detail": "هیئت مربوط به کاربر یافت نشد."}, status=404)

        # player/coach/referee/both
        try:
            profile = UserProfile.objects.get(user=user)
            serializer = PlayerDashboardSerializer(profile, context={"request": request})

            student_count = UserProfile.objects.filter(coach=profile).count() if profile.is_coach else 0
            coaching_clubs_count = profile.coaching_clubs.count() if profile.is_coach else 0

            return Response({**serializer.data, "student_count": student_count, "coaching_clubs_count": coaching_clubs_count})
        except UserProfile.DoesNotExist:
            return Response({"detail": "پروفایل پیدا نشد."}, status=404)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_profile_with_form_data_view(request):
    try:
        user = request.user
        profile = user.profile
    except UserProfile.DoesNotExist:
        return Response({"detail": "پروفایل یافت نشد."}, status=404)

    profile_serializer = UserProfileSerializer(profile, context={'request': request})
    heyats = list(TkdBoard.objects.values('id', 'name'))
    clubs = list(TkdClub.objects.values('id', 'club_name'))

    gender = profile.gender
    coaches_qs = UserProfile.objects.filter(is_coach=True, gender=gender)
    coaches = [{"id": coach.id, "full_name": f"{coach.first_name} {coach.last_name}"} for coach in coaches_qs]

    BELT_CHOICES = [
        ('زرد', 'زرد'), ('سبز', 'سبز'), ('آبی', 'آبی'), ('قرمز', 'قرمز'),
        *[(f'مشکی دان {i}', f'مشکی دان {i}') for i in range(1, 11)]
    ]
    DEGREE_CHOICES = [('درجه یک', 'درجه یک'), ('درجه دو', 'درجه دو'), ('درجه سه', 'درجه سه'), ('ممتاز', 'ممتاز')]

    return Response({
        "profile": profile_serializer.data,
        "form_options": {
            "heyats": heyats,
            "clubs": clubs,
            "coaches": coaches,
            "belt_choices": BELT_CHOICES,
            "degree_choices": DEGREE_CHOICES,
        }
    })



logger = logging.getLogger(__name__)


class UpdateProfilePendingAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _is_junk_str(self, v):
        return isinstance(v, str) and v.strip().lower() in ("", "null", "none", "undefined")

    def _parse_json_maybe(self, v, default):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return default
        return v if v is not None else default

    def post(self, request):
        # -----------------------
        # load original profile
        # -----------------------
        try:
            original = request.user.profile
        except Exception:
            return Response({"error": "پروفایل یافت نشد."}, status=404)

        data = request.data.copy()

        # -----------------------
        # profile_image: فقط اگر فایل واقعی آمده باشد
        # -----------------------
        if "profile_image" not in request.FILES:
            data.pop("profile_image", None)
        else:
            # اگر برخی فرانت‌ها همزمان string هم می‌فرستن، پاکش کن تا فایل بماند
            if self._is_junk_str(data.get("profile_image")):
                data.pop("profile_image", None)

        # -----------------------
        # refereeTypes (string->dict)
        # -----------------------
        referee_types = self._parse_json_maybe(data.get("refereeTypes"), default={})
        if not isinstance(referee_types, dict):
            referee_types = {}
        data["refereeTypes"] = referee_types

        # -----------------------
        # selected clubs:
        # - پشتیبانی از selectedClubs[] (form)
        # - یا selectedClubs (json string)
        # -----------------------
        clubs = []
        if hasattr(request.data, "getlist"):
            clubs = request.data.getlist("selectedClubs[]") or []

        if not clubs:
            clubs_raw = data.get("selectedClubs")
            parsed = self._parse_json_maybe(clubs_raw, default=[])
            if isinstance(parsed, (list, tuple)):
                clubs = list(parsed)

        # normalize -> int list
        club_ids = [int(x) for x in clubs if str(x).isdigit()]
        # ⚠️ این فیلد احتمالاً توی مدل PendingEditProfile نیست؛ برای serializer نفرست
        data.pop("selectedClubs", None)

        # -----------------------
        # coach levels mapping
        # -----------------------
        if data.get("coachGradeNational"):
            data["coach_level"] = data.get("coachGradeNational")
        if data.get("coachGradeIntl"):
            data["coach_level_International"] = data.get("coachGradeIntl")

        # -----------------------
        # extract referee flags + levels from refereeTypes
        # -----------------------
        for field in ["kyorogi", "poomseh", "hanmadang"]:
            selected = bool((referee_types.get(field) or {}).get("selected", False))
            data[field] = selected
            if selected:
                data[f"{field}_level"] = (referee_types.get(field) or {}).get("gradeNational") or None
                data[f"{field}_level_International"] = (referee_types.get(field) or {}).get("gradeIntl") or None
            else:
                # اگر انتخاب نشده، level ها را پاک کن تا diff درست باشد
                data[f"{field}_level"] = None
                data[f"{field}_level_International"] = None

        # -----------------------
        # coach (FK)
        # -----------------------
        coach_id = data.get("coach")
        if coach_id == "other" or self._is_junk_str(coach_id):
            data["coach"] = None
        elif coach_id and str(coach_id).isdigit():
            data["coach"] = int(coach_id)
        else:
            # اگر چیزی نامعتبر است، حذفش کن تا serializer گیر ندهد
            data.pop("coach", None)

        # -----------------------
        # upsert pending
        # -----------------------
        existing = PendingEditProfile.objects.filter(original_user=original).first()
        serializer = PendingEditProfileSerializer(
            existing, data=data, partial=True, context={"request": request}
        ) if existing else PendingEditProfileSerializer(
            data=data, context={"request": request}
        )

        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=400)

        pending = serializer.save(original_user=original)

        # -----------------------
        # validate/assign coach instance + prevent coach=self
        # -----------------------
        if coach_id and str(coach_id).isdigit():
            try:
                coach_obj = UserProfile.objects.get(id=int(coach_id))
                if coach_obj.phone == original.phone:
                    return Response({"status": "error", "message": "مربی نمی‌تواند خودش باشد."}, status=400)
                pending.coach = coach_obj
                pending.coach_name = f"{coach_obj.first_name} {coach_obj.last_name}".strip()
            except UserProfile.DoesNotExist:
                # مربی نامعتبر → پاک
                pending.coach = None

        # -----------------------
        # set M2M coaching_clubs
        # -----------------------
        if hasattr(pending, "coaching_clubs"):
            pending.coaching_clubs.set(club_ids)

        # -----------------------
        # club_names + default club انتخابی
        # -----------------------
        club_names = []
        if club_ids:
            club_names = list(
                TkdClub.objects.filter(id__in=club_ids).values_list("club_name", flat=True)
            )

        club_id = data.get("club")
        if club_id and str(club_id).isdigit():
            try:
                pending.club = TkdClub.objects.get(id=int(club_id))
                if pending.club and pending.club.club_name not in club_names:
                    club_names.append(pending.club.club_name)
            except TkdClub.DoesNotExist:
                pass
        elif club_ids:
            try:
                pending.club = TkdClub.objects.get(id=club_ids[0])
            except TkdClub.DoesNotExist:
                pass

        pending.club_names = club_names

        # -----------------------
        # derive role based on flags (optional)
        # -----------------------
        if getattr(pending, "is_coach", False) and getattr(pending, "is_referee", False):
            pending.role = "both"
        elif getattr(pending, "is_coach", False):
            pending.role = "coach"
        elif getattr(pending, "is_referee", False):
            pending.role = "referee"
        else:
            pending.role = "player"

        if pending.tkd_board:
            pending.tkd_board_name = pending.tkd_board.name

        pending.save()

        return Response(
            {"status": "ok", "message": "درخواست ویرایش شما ثبت و در انتظار تایید است."},
            status=200
        )

@staff_member_required
def approve_edited_profile(request, pk):
    pending = get_object_or_404(PendingEditProfile, pk=pk)
    user = pending.original_user

    if not user:
        messages.error(request, "پروفایل اصلی یافت نشد.")
        return redirect(reverse("admin:accounts_pendingeditprofile_changelist"))

    simple_fields = [
        'first_name', 'last_name', 'father_name', 'birth_date', 'gender',
        'address', 'province', 'county', 'city',
        'belt_grade', 'belt_certificate_number', 'belt_certificate_date',
        'coach_level', 'coach_level_International',
        'kyorogi', 'kyorogi_level', 'kyorogi_level_International',
        'poomseh', 'poomseh_level', 'poomseh_level_International',
        'hanmadang', 'hanmadang_level', 'hanmadang_level_International',
        'is_coach', 'is_referee', 'tkd_board_name', 'club_names', 'confirm_info', 'role'
    ]

    for field in simple_fields:
        setattr(user, field, getattr(pending, field))

    if pending.tkd_board_id:
        user.tkd_board = pending.tkd_board
    if pending.coach_id:
        user.coach = pending.coach
        user.coach_name = pending.coach_name
    if pending.club_id:
        user.club = pending.club

    if pending.profile_image:
        user.profile_image = pending.profile_image

    if pending.coaching_clubs.exists():
        user.coaching_clubs.set(pending.coaching_clubs.all())

    user.save()
    pending.delete()

    messages.success(request, "ویرایش کاربر با موفقیت تایید شد.")
    return redirect(reverse("admin:accounts_userprofile_changelist"))


class CoachStudentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            coach_profile = user.profile
        except UserProfile.DoesNotExist:
            return Response({"error": "پروفایل یافت نشد."}, status=404)

        if not coach_profile.is_coach:
            return Response({"error": "فقط مربیان به این بخش دسترسی دارند."}, status=403)

        # ✅ هر نقشی (player/coach/referee/both) اگر coach این مربی باشد نمایش داده شود
        # ✅ خود مربی حتی اگر coach خودش را خودش زده باشد، در لیست خودش نمایش داده نشود
        students = UserProfile.objects.filter(coach=coach_profile).exclude(pk=coach_profile.pk)

        club = request.GET.get("club")
        if club and club != "باشگاه":
            students = students.filter(club__club_name=club)

        belt = request.GET.get("belt")
        if belt and belt != "درجه کمربند":
            students = students.filter(belt_grade=belt)

        birth_from = request.GET.get("birth_from")
        if birth_from:
            students = students.filter(birth_date__gte=birth_from)

        birth_to = request.GET.get("birth_to")
        if birth_to:
            students = students.filter(birth_date__lte=birth_to)

        search = request.GET.get("search")
        if search:
            students = students.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(national_code__icontains=search)
            )

        students = annotate_student_stats(students)
        serialized = ClubStudentSerializer(students, many=True)
        return Response(serialized.data)


class CoachClubsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            coach = request.user.profile
            if not coach.is_coach:
                return Response({"error": "شما مربی نیستید."}, status=403)

            clubs = coach.coaching_clubs.all()
            return Response(ClubSerializer(clubs, many=True).data)
        except Exception:
            return Response({"error": "خطا در دریافت باشگاه‌ها"}, status=400)


class AllClubsAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(ClubSerializer(TkdClub.objects.all(), many=True).data)


class UpdateCoachClubsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        coach = request.user.profile
        if not coach.is_coach:
            return Response({"error": "شما مربی نیستید."}, status=403)

        club_ids = request.data.get("coaching_clubs", [])
        if not isinstance(club_ids, list) or len(club_ids) > 3:
            return Response({"error": "حداکثر ۳ باشگاه مجاز است."}, status=400)

        clubs = TkdClub.objects.filter(id__in=club_ids)
        coach.coaching_clubs.set(clubs)
        return Response({"message": "باشگاه‌ها با موفقیت بروزرسانی شدند."})


class UpdateClubCoachesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            club = TkdClub.objects.get(user=request.user)
        except TkdClub.DoesNotExist:
            return Response({"detail": "باشگاه یافت نشد."}, status=404)

        selected_ids = request.data.get("selected_coaches", [])
        if not isinstance(selected_ids, list):
            return Response({"detail": "داده‌ها معتبر نیستند."}, status=400)

        all_coaches = UserProfile.objects.filter(is_coach=True)
        active_ids = set(club.coaches.values_list('id', flat=True))

        selected_ids_set = set(selected_ids)
        to_add = selected_ids_set - active_ids
        to_remove = active_ids - selected_ids_set

        for coach_id in to_add:
            coach = UserProfile.objects.filter(id=coach_id).first()
            if coach and coach.coaching_clubs.count() >= 3:
                continue
            CoachClubRequest.objects.get_or_create(
                coach=coach, club=club, request_type='add', defaults={"status": "pending"}
            )

        for coach_id in to_remove:
            coach = UserProfile.objects.filter(id=coach_id).first()
            CoachClubRequest.objects.get_or_create(
                coach=coach, club=club, request_type='remove', defaults={"status": "pending"}
            )

        return Response({"detail": "درخواست‌ها با موفقیت ثبت شدند."})


class PendingCoachRequestsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # امن: اگر پروفایل یا مربی نبود، لیست خالی برگردون
        try:
            user_profile = request.user.profile
        except UserProfile.DoesNotExist:
            return Response([], status=200)

        if not getattr(user_profile, "is_coach", False):
            return Response([], status=200)

        requests = CoachClubRequest.objects.filter(
            coach=user_profile,
            status='pending',
        )
        serializer = CoachClubRequestSerializer(requests, many=True)
        return Response(serializer.data)


class RespondToCoachRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user_profile = request.user.profile
        action = request.data.get("action")  # "accept" | "reject"

        try:
            req = CoachClubRequest.objects.get(id=pk, coach=user_profile, status='pending')
        except CoachClubRequest.DoesNotExist:
            return Response({"detail": "درخواست یافت نشد."}, status=404)

        if action == "accept":
            if req.request_type == "add":
                user_profile.coaching_clubs.add(req.club)
            elif req.request_type == "remove":
                user_profile.coaching_clubs.remove(req.club)
            req.status = 'accepted'
            req.save()
            return Response({"detail": "درخواست تأیید شد."})

        if action == "reject":
            req.status = 'rejected'
            req.save()
            return Response({"detail": "درخواست رد شد."})

        return Response({"detail": "دستور نامعتبر است."}, status=400)


# ---------- Heyat (Board) ----------
@method_decorator(csrf_exempt, name='dispatch')
class HeyatLoginAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    # ✅ برای اطمینان، پاسخ به preflight
    def options(self, request, *args, **kwargs):
        return Response(status=204)

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:
            return Response({"error": "نام کاربری و رمز عبور الزامی هستند."}, status=400)

        user = authenticate(username=username, password=password)
        if not user:
            return Response({"error": "نام کاربری یا رمز عبور اشتباه است."}, status=401)

        try:
            board = TkdBoard.objects.get(user=user)
        except TkdBoard.DoesNotExist:
            return Response({"error": "هیأت مرتبط یافت نشد."}, status=403)

        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "role": "heyat",
            "board_id": board.id,
            "board_name": board.name
        })


class HeyatStudentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            board = TkdBoard.objects.get(user=request.user)
        except TkdBoard.DoesNotExist:
            return Response({"detail": "هیئت پیدا نشد"}, status=404)

        students = UserProfile.objects.filter(role='player', tkd_board=board)

        coach = request.GET.get("coach")
        if coach and coach != "مربی":
            students = students.annotate(
                full_name=Concat('coach__first_name', Value(' '), 'coach__last_name', output_field=CharField())
            ).filter(full_name__icontains=coach)

        club = request.GET.get("club")
        if club and club != "باشگاه":
            students = students.filter(club__club_name=club)

        belt = request.GET.get("belt")
        if belt and belt != "درجه کمربند":
            students = students.filter(belt_grade=belt)

        birth_from = request.GET.get("birth_from")
        if birth_from:
            students = students.filter(birth_date__gte=birth_from)

        birth_to = request.GET.get("birth_to")
        if birth_to:
            students = students.filter(birth_date__lte=birth_to)

        search = request.GET.get("search")
        if search:
            students = students.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(national_code__icontains=search)
            )

        students = annotate_student_stats(students)
        serialized = ClubStudentSerializer(students, many=True)
        return Response(serialized.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def heyat_form_data(request):
    try:
        board = TkdBoard.objects.get(user=request.user)
    except TkdBoard.DoesNotExist:
        return Response({"detail": "هیئت یافت نشد"}, status=404)

    coaches = UserProfile.objects.filter(tkd_board=board, is_coach=True)
    clubs = TkdClub.objects.filter(tkd_board=board)

    coach_names = [{"id": c.id, "name": f"{c.first_name} {c.last_name}"} for c in coaches]
    club_names = [{"id": c.id, "club_name": c.club_name} for c in clubs]

    return Response({"coaches": coach_names, "clubs": club_names})


class HeyatCoachesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            board = TkdBoard.objects.get(user=request.user)
        except TkdBoard.DoesNotExist:
            return Response({"detail": "هیئت یافت نشد"}, status=404)

        coaches = UserProfile.objects.filter(
            tkd_board=board, is_coach=True,
        ).prefetch_related("coaching_clubs")

        club = request.GET.get("club")
        if club and club != "همه":
            coaches = coaches.filter(coaching_clubs__club_name=club)

        belt = request.GET.get("belt")
        if belt and belt != "همه":
            coaches = coaches.filter(belt_grade=belt)

        birth_from = request.GET.get("birth_from")
        if birth_from:
            coaches = coaches.filter(birth_date__gte=birth_from)

        birth_to = request.GET.get("birth_to")
        if birth_to:
            coaches = coaches.filter(birth_date__lte=birth_to)

        national_level = request.GET.get("national_level")
        if national_level and national_level != "همه":
            coaches = coaches.filter(coach_level=national_level)

        international_level = request.GET.get("international_level")
        if international_level and international_level != "همه":
            coaches = coaches.filter(coach_level_International=international_level)

        search = request.GET.get("search")
        if search:
            coaches = coaches.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(national_code__icontains=search)
            )

        result = []
        for coach in coaches.distinct():
            result.append({
                "full_name": f"{coach.first_name} {coach.last_name}",
                "national_code": coach.national_code,
                "birth_date": coach.birth_date,
                "belt_grade": coach.belt_grade,
                "national_certificate_date": coach.coach_level or "—",
                "international_certificate_date": coach.coach_level_International or "درجه بین‌الملل ندارد",
                "clubs": [club.club_name for club in coach.coaching_clubs.all()]
            })
        return Response(result)


class HeyatRefereesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            board = TkdBoard.objects.get(user=request.user)
        except TkdBoard.DoesNotExist:
            return Response({"detail": "هیئت یافت نشد"}, status=404)

        referees = UserProfile.objects.filter(tkd_board=board, is_referee=True)

        club = request.GET.get("club")
        if club and club != "همه":
            referees = referees.filter(belt_grade=belt)

        belt = request.GET.get("belt")
        if belt and belt != "همه":
            referees = referees.filter(belt_grade=belt)

        birth_from = request.GET.get("birth_from")
        if birth_from:
            referees = referees.filter(birth_date__gte=birth_from)

        birth_to = request.GET.get("birth_to")
        if birth_to:
            referees = referees.filter(birth_date__lte=birth_to)

        search = request.GET.get("search")
        if search:
            referees = referees.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(national_code__icontains=search)
            )

        referee_field = request.GET.get("referee_field")
        if referee_field and referee_field != "همه":
            field_map = {"کیوروگی": "kyorogi", "پومسه": "poomseh", "هانمادانگ": "hanmadang"}
            field_key = field_map.get(referee_field)
            if field_key:
                referees = referees.filter(**{f"{field_key}": True})

        national_level = request.GET.get("national_level")
        international_level = request.GET.get("international_level")

        if national_level and national_level != "همه":
            referees = referees.filter(
                Q(kyorogi_level=national_level) |
                Q(poomseh_level=national_level) |
                Q(hanmadang_level=national_level)
            )

        if international_level and international_level != "همه":
            referees = referees.filter(
                Q(kyorogi_level_International=international_level) |
                Q(poomseh_level_International=international_level) |
                Q(hanmadang_level_International=international_level)
            )

        result = []
        for r in referees:
            result.append({
                "full_name": f"{r.first_name} {r.last_name}",
                "national_code": r.national_code,
                "birth_date": r.birth_date,
                "belt_grade": r.belt_grade,
                "clubs": [c.club_name for c in r.coaching_clubs.all()],
                "referee_fields": {
                    "کیوروگی": {
                        "active": r.kyorogi,
                        "national": r.kyorogi_level or "درجه ملی ندارد",
                        "international": r.kyorogi_level_International or "درجه بین‌الملل ندارد"
                    },
                    "پومسه": {
                        "active": r.poomseh,
                        "national": r.poomseh_level or "درجه ملی ندارد",
                        "international": r.poomseh_level_International or "درجه بین‌الملل ندارد"
                    },
                    "هانمادانگ": {
                        "active": r.hanmadang,
                        "national": r.hanmadang_level or "درجه ملی ندارد",
                        "international": r.hanmadang_level_International or "درجه بین‌الملل ندارد"
                    },
                }
            })
        return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def heyat_clubs_list(request):
    try:
        board = TkdBoard.objects.get(user=request.user)
    except TkdBoard.DoesNotExist:
        return Response({"detail": "هیئت یافت نشد."}, status=403)

    clubs = TkdClub.objects.filter(tkd_board=board)

    search = request.GET.get("search")
    if search:
        clubs = clubs.filter(
            Q(club_name__icontains=search) |
            Q(founder_name__icontains=search) |
            Q(founder_phone__icontains=search)
        )

    data = []
    for club in clubs:
        student_count = UserProfile.objects.filter(club=club, role="player").count()
        coach_count = UserProfile.objects.filter(coaching_clubs=club, is_coach=True).count()

        data.append({
            "id": club.id,
            "club_name": club.club_name,
            "manager_name": club.founder_name,
            "phone": club.phone,
            "manager_phone": club.founder_phone,
            "student_count": student_count,
            "coach_count": coach_count
        })

    return Response(data, status=200)


class KyorugiCompetitionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = UserProfile.objects.select_related('coach').filter(user=request.user).first()

        role = None
        is_coach = False
        if profile:
            role = profile.role
            is_coach = bool(profile.is_coach or role in ['coach', 'both'])
        elif TkdClub.objects.filter(user=request.user).exists():
            role = 'club'
        elif TkdBoard.objects.filter(user=request.user).exists():
            role = 'heyat'
        else:
            return Response([])

        qs = KyorugiCompetition.objects.all().order_by('-id')

        if is_coach:
            pass
        elif role == 'player':
            if profile and profile.coach_id:
                qs = qs.filter(
                    coach_approvals__coach=profile.coach,
                    coach_approvals__is_active=True,
                    coach_approvals__terms_accepted=True,
                ).distinct()
            else:
                qs = qs.none()
        elif role == 'referee':
            today = now().date()
            qs = qs.filter(
                registration_open=True,
                registration_start__lte=today,
                registration_end__gte=today,
            )
        elif role in ['club', 'heyat']:
            pass

        data = DashboardKyorugiCompetitionSerializer(qs, many=True, context={'request': request}).data
        return Response(data)


# ---------- Mini Profile ----------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mini_profile(request):
    u = request.user
    prof = getattr(u, "profile", None) or UserProfile.objects.filter(user=u).first()

    if not prof:
        full_name = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip()
        return Response({
            "full_name": full_name or (getattr(u, "username", "") or ""),
            "first_name": (u.first_name or "").strip(),
            "last_name": (u.last_name or "").strip(),
            "national_code": "",
            "belt_grade": "",
            "role": "",
            "profile_image_url": None,
        })

    def abs_url(filefield):
        try:
            if filefield and getattr(filefield, "url", None):
                return request.build_absolute_uri(filefield.url)
        except Exception:
            pass
        return None

    data = {
        "full_name": f"{(prof.first_name or '').strip()} {(prof.last_name or '').strip()}".strip(),
        "first_name": (prof.first_name or "").strip(),
        "last_name": (prof.last_name or "").strip(),
        "national_code": (prof.national_code or "").strip(),
        "belt_grade": (prof.belt_grade or "").strip(),
        "role": (prof.role or "").strip(),
        "profile_image_url": abs_url(getattr(prof, "profile_image", None)),
    }
    return Response(data)


# ---------- Universal Login (with Role Gate + Debug Echo) ----------

@method_decorator(csrf_exempt, name='dispatch')
class UniversalLoginAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    ROLE_GROUPS = {
        "player": {"player"},
        "coachref": {"coach", "referee", "both"},
        "club": {"club"},
        "heyat": {"heyat", "board"},
    }

    ROLE_PRIORITY = ["club", "heyat", "coach", "referee", "both", "player"]

    # ✅ برای اطمینان، پاسخ به preflight
    def options(self, request, *args, **kwargs):
        return Response(status=204)

    def _roles_of(self, user):
        roles = set()
        prof = getattr(user, "profile", None)

        if prof:
            r = (prof.role or "").strip().lower()
            if r == "both":
                roles.update({"coach", "referee", "both"})
            elif r in {"player", "coach", "referee"}:
                roles.add(r)

        if TkdClub.objects.filter(user=user).exists():
            roles.add("club")
        if TkdBoard.objects.filter(user=user).exists():
            roles.add("heyat")

        if not roles:
            roles.add("player")
        return roles

    def _pick_role_for_response(self, allowed_hit: set, user_roles: set, req_group: str):
        if req_group in self.ROLE_GROUPS:
            group_roles = self.ROLE_GROUPS[req_group]
            inter = (user_roles & group_roles) or allowed_hit
            if inter:
                for r in self.ROLE_PRIORITY:
                    if r in inter:
                        return r
        for r in self.ROLE_PRIORITY:
            if r in user_roles:
                return r
        return "player"

    def post(self, request):
        username = _normalize_digits(
            request.data.get("username") or request.data.get("identifier") or ""
        )
        password = _normalize_digits(request.data.get("password") or "")
        otp = _normalize_digits(request.data.get("otp") or "")

        req_group = (
            (request.headers.get("X-Role-Group") or "")
            or (request.data.get("roleGroup") or "")
            or (request.query_params.get("roleGroup") or "")
        ).strip().lower()

        if not username and not otp:
            return Response({"error": "identifier/username الزامی است."}, status=400)
        if not password and not otp:
            return Response({"error": "password یا otp لازم است."}, status=400)
        if not req_group:
            return Response({"error": "roleGroup ارسال نشده است."}, status=400)
        if req_group not in self.ROLE_GROUPS:
            return Response({"error": "roleGroup نامعتبر است."}, status=400)

        user = authenticate(username=username, password=password) if password else None
        if not user:
            return Response({"error": "نام کاربری یا رمز عبور اشتباه است."}, status=401)

        user_roles = self._roles_of(user)
        allowed = self.ROLE_GROUPS[req_group]

        hit = user_roles & allowed
        if not hit:
            return Response(
                {
                    "error": "این فرم برای نقش دیگری است. لطفاً از فرم صحیح ورود استفاده کنید.",
                    "user_roles": sorted(user_roles),
                    "required_any_of": sorted(allowed),
                },
                status=403,
            )

        refresh = RefreshToken.for_user(user)
        chosen_role = self._pick_role_for_response(hit, user_roles, req_group)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "role": chosen_role,
                "roles": sorted(user_roles),
                "ts": now().isoformat(),
            },
            status=200,
        )


# ---------- Forgot Password (SMS) ----------

class ForgotPasswordSendCodeAPIView(APIView):
    """ارسال کد برای فراموشی رمز عبور (شماره باید موجود باشد)."""
    permission_classes = [AllowAny]

    def post(self, request):
        cleanup_expired_sms()
        phone = (request.data.get("phone") or "").strip()
        if not phone.isdigit() or not phone.startswith("09") or len(phone) != 11:
            return Response({"error": "شماره موبایل معتبر نیست."}, status=400)

        user = User.objects.filter(username=phone).first()
        if not user:
            prof = UserProfile.objects.filter(phone=phone).select_related("user").first()
            club = TkdClub.objects.filter(founder_phone=phone).select_related("user").first()
            if prof and prof.user:
                user = prof.user
            elif club and club.user:
                user = club.user

        if not user:
            return Response({"error": "کاربری با این شماره یافت نشد."}, status=404)

        # 🔁 Rate limit 3 دقیقه
        recent = SMSVerification.objects.filter(
            phone=phone, created_at__gte=timezone.now() - timedelta(minutes=3)
        ).first()
        if recent:
            remaining = 180 - int((timezone.now() - recent.created_at).total_seconds())
            return Response({"error": "کد قبلی هنوز معتبر است.", "retry_after": remaining}, status=429)

        code = generate_unique_sms_code(phone)
        SMSVerification.objects.create(phone=phone, code=code)
        send_verification_code(phone, code)

        return Response({"message": "کد تأیید ارسال شد."}, status=200)


class ForgotPasswordVerifyAPIView(APIView):
    """
    تایید کد و بازنشانی رمز:
    - player/coach/referee → رمز = کدملی پروفایل
    - club → رمز = کدملی موسس
    - در نبود کدملی → رمز موقت
    """
    permission_classes = [AllowAny]

    def post(self, request):
        cleanup_expired_sms()
        phone = (request.data.get("phone") or "").strip()
        code = (request.data.get("code") or "").strip()

        if not phone.isdigit() or not phone.startswith("09") or len(phone) != 11:
            return Response({"error": "شماره موبایل معتبر نیست."}, status=400)
        if not code.isdigit() or len(code) != 4:
            return Response({"error": "کد باید ۴ رقمی باشد."}, status=400)

        expire_time = timezone.now() - timedelta(minutes=3)
        try:
            rec = SMSVerification.objects.get(phone=phone, code=code)
        except SMSVerification.DoesNotExist:
            SMSVerification.objects.filter(phone=phone).delete()
            return Response({"error": "کد وارد شده نادرست است."}, status=400)

        if rec.created_at < expire_time:
            rec.delete()
            return Response({"error": "کد منقضی شده است. لطفاً مجدداً دریافت کنید."}, status=400)

        rec.delete()

        user = User.objects.filter(username=phone).first()
        prof = None
        club = None
        if not user:
            prof = UserProfile.objects.filter(phone=phone).select_related("user").first()
            club = TkdClub.objects.filter(founder_phone=phone).select_related("user").first()
            if prof and prof.user:
                user = prof.user
            elif club and club.user:
                user = club.user

        if not user:
            return Response({"error": "کاربری با این شماره یافت نشد."}, status=404)

        if not prof:
            prof = getattr(user, "profile", None)
        if not club:
            club = TkdClub.objects.filter(user=user).first()

        new_pass = None
        if prof:
            new_pass = _normalize_digits(prof.national_code)
        elif club:
            new_pass = _normalize_digits(club.founder_national_code)

        if not new_pass:
            new_pass = f"Temp#{phone[-4:]}"

        user.set_password(new_pass)
        user.save()

        role = _detect_role(user)

        return Response(
            {"username": user.username, "password": new_pass, "role": role, "message": "رمز عبور شما بازنشانی شد."},
            status=200,
        )
