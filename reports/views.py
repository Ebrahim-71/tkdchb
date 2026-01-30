# tkdjango/reports/views.py
import csv
from datetime import date, timedelta
from django.utils.html import format_html
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import render, redirect

from .forms import DateRangeForm, CoachStudentsForm, ClubStudentsForm, BoardStudentsForm
from .forms import BoardCoachesRefereesForm   # ← جدید
from . import services


def _admin_ctx(request):
    return admin.site.each_context(request)

def _daterange_from_form(request):
    form = DateRangeForm(request.GET or None)
    try:
        form.is_valid()
    except Exception:
        pass
    cd = getattr(form, "cleaned_data", {}) or {}
    s, e = cd.get("start"), cd.get("end")
    if not s and not e:
        e = date.today()
        s = e - timedelta(days=30)
    return form, s, e

@staff_member_required
def center(request):
    ctx = _admin_ctx(request)
    ctx.update({"title": "مرکز گزارش‌گیری"})
    return render(request, "admin/reports/center.html", ctx)


@staff_member_required
def users_report(request):
    form, start, end = _daterange_from_form(request)
    data = services.users_summary(start, end)

    # --- شاگردان اساتید ---
    coach_form = CoachStudentsForm(request.GET or None, prefix="cs")
    students = None
    coach_display = None
    if request.GET.get("show_students") == "1":
        if coach_form.is_valid():
            cd = coach_form.cleaned_data
            coach = cd.get("coach")
            belt  = cd.get("belt")
            club  = cd.get("club")
            coach_display = str(coach) if coach else None

            students = services.coach_students(
                coach_id      = coach.id if coach else None,
                belt_id       = belt,
                club_id       = getattr(club, "id", None) if club else None,
                national_code = cd.get("national_code") or None,
            )
        else:
            students = {"rows": []}

    # --- شاگردان باشگاه‌ها ---
    club_form  = ClubStudentsForm(request.GET or None, prefix="cl")
    club_students = None
    club_display = None
    if request.GET.get("show_club_students") == "1":
        if club_form.is_valid():
            cd = club_form.cleaned_data
            club  = cd.get("club")
            belt  = cd.get("belt")
            coach = cd.get("coach")
            club_display = str(club) if club else None

            club_students = services.club_students(
                club_id       = getattr(club, "id", None) if club else None,
                belt_id       = belt,
                coach_id      = coach.id if coach else None,
                national_code = cd.get("national_code") or None,
            )
        else:
            club_students = {"rows": []}

    # --- شاگردان هیئت‌ها ---
    board_form = BoardStudentsForm(request.GET or None, prefix="bd")
    board_students = None
    board_display = None
    if request.GET.get("show_board_students") == "1":
        if board_form.is_valid():
            cd = board_form.cleaned_data
            board = cd.get("board")
            belt  = cd.get("belt")
            coach = cd.get("coach")
            club  = cd.get("club")
            ncode = cd.get("national_code")
            board_display = str(board) if board else None

            board_students = services.board_students(
                board_id      = board.id if board else None,
                belt_id       = belt,
                coach_id      = coach.id if coach else None,
                club_id       = getattr(club, "id", None) if club else None,
                national_code = ncode or None,
            )
        else:
            board_students = {"rows": []}

    # --- مربی و داور هیئت‌ها  ← جدید ---
    cr_form = BoardCoachesRefereesForm(request.GET or None, prefix="cr")
    board_coaches_referees = None
    role_display = None
    board_display_for_cr = None
    if request.GET.get("show_board_coaches_referees") == "1":
        if cr_form.is_valid():
            cd = cr_form.cleaned_data
            board = cd.get("board")
            role  = cd.get("role") or ""
            club  = cd.get("club")
            ncode = cd.get("national_code") or None

            board_display_for_cr = str(board) if board else None
            role_display = "فقط مربی" if role=="coach" else ("فقط داور" if role=="referee" else None)

            board_coaches_referees = services.board_coaches_referees(
                board_id = board.id if board else None,
                role     = role or None,
                club_id  = getattr(club, "id", None) if club else None,
                national_code = ncode,
            )
        else:
            board_coaches_referees = {"rows": []}

    ctx = {
        "form": form,
        "data": data,

        "coach_form": coach_form,
        "students": students,
        "coach_display": coach_display,

        "club_form": club_form,
        "club_students": club_students,
        "club_display": club_display,

        "board_form": board_form,
        "board_students": board_students,
        "board_display": board_display,

        # 👇 جدید:
        "cr_form": cr_form,
        "board_coaches_referees": board_coaches_referees,
        "role_display": role_display,
        # اگر در تمپلیت یک متغیر واحد board_display استفاده می‌کنی، می‌توانی این را هم بگذاری:
        "board_display_for_cr": board_display_for_cr,
    }
    return render(request, "admin/reports/users.html", ctx)


@staff_member_required
def competitions_report(request):
    form, s, e = _daterange_from_form(request)
    data = services.competitions_summary(s, e)
    ctx = _admin_ctx(request)
    ctx.update({"title": "گزارش مسابقات", "form": form, "data": data})
    return render(request, "admin/reports/competitions.html", ctx)

@staff_member_required
def finance_report(request):
    form, s, e = _daterange_from_form(request)
    data = services.finance_summary(s, e)
    ctx = _admin_ctx(request)
    ctx.update({"title": "گزارش مالی", "form": form, "data": data})
    return render(request, "admin/reports/finance.html", ctx)

@staff_member_required
def export_csv(request, kind: str):
    form, s, e = _daterange_from_form(request)

    if kind == "users":
        res = services.users_summary(s, e)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="users_report.csv"'
        w = csv.writer(response)
        w.writerow(["from", "to", "total"])
        w.writerow([res["start"], res["end"], res["total"]])
        w.writerow([])
        w.writerow(["role", "count"])
        for row in res["by_role"]:
            # در users_summary کلید شمارش "c" است
            w.writerow([row.get("role") or "", row.get("c") or 0])
        return response

    if kind == "competitions":
        res = services.competitions_summary(s, e)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="competitions_report.csv"'
        w = csv.writer(response)
        w.writerow(["from", "to", "total"])
        w.writerow([res["start"], res["end"]])
        w.writerow([])
        w.writerow(["status", "count"])
        for row in res["by_status"]:
            w.writerow([row.get("status") or "نامشخص", row.get("c")])
        w.writerow([])
        w.writerow(["competition", "enrollment_count"])
        for row in res["top_by_enroll"]:
            w.writerow([row["competition"], row["count"]])
        return response

    if kind == "finance":
        res = services.finance_summary(s, e)
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="finance_report.csv"'
        w = csv.writer(response)
        w.writerow(["from", "to"])
        w.writerow([res["start"], res["end"]])
        w.writerow([])
        w.writerow(["metric", "value"])
        w.writerow(["enrollment_paid_count", res["enrollment_paid_count"]])
        w.writerow(["enrollment_paid_sum",  res["enrollment_paid_sum"]])
        w.writerow(["seminar_paid_count",   res["seminar_paid_count"]])
        w.writerow(["seminar_paid_sum",     res["seminar_paid_sum"]])
        return response

    return redirect("reports:center")
