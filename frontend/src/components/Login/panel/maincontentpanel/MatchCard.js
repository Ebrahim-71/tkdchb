// src/components/Login/panel/maincontentpanel/MatchCard.jsx
import React from "react";
import { Link } from "react-router-dom";
import "../../../../api/competitions";
import { API_BASE as API_ROOT } from "../../../../api/competitions";
import "./MatchCard.css";

// --- helpers (لوکال) ---
const toPersianDigits = (str) =>
  String(str ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);

const fmtDateFa = (val) => {
  if (!val) return "—";
  const s = String(val).slice(0, 10).replace(/-/g, "/");
  return toPersianDigits(s);
};

function getRole() {
  return localStorage.getItem("user_role") || "player";
}

function isKyorugi(match) {
  const s = String(match?.style_display || match?.style || "")
    .trim()
    .toLowerCase();
  return s.includes("کیوروگی") || s.includes("kyorugi") || s.includes("kyor");
}

function pickImageSrc(match) {
  const poster =
    match?.poster_url ??
    match?.poster ??
    match?.cover ??
    match?.image ??
    "";

  if (typeof poster === "string" && poster.startsWith("http")) return poster;
  if (typeof poster === "string" && poster.startsWith("/"))
    return `${API_ROOT}${poster}`;
  return "/placeholder.jpg";
}

const MatchCard = ({ match, onDetailsClick }) => {
  const slug = match?.public_id;
  const role = getRole();
  const ky = isKyorugi(match);

  // عنوان
  const title = match?.title || match?.name || "—";

  // کمربند
  const beltText = ky
    ? match?.belt_level_display ||
      match?.belt_group_name ||
      match?.belt_groups_display ||
      "—"
    : match?.belt_groups_display ||
      match?.belt_group_name ||
      match?.belt_level_display ||
      "—";

  // 👇 گروه سنی فقط برای پومسه
  const ageText = !ky
    ? match?.age_group_display ||
      match?.age_categories_display ||
      match?.age_category_name ||
      "—"
    : null;

  const imageSrc = pickImageSrc(match);

  const drawDate = match?.draw_date_jalali ?? match?.draw_date ?? null;

  // محل برگزاری: فقط شهر
  const city = match?.city || "";

  // مبلغ ورودی
  const fee = match?.entry_fee != null ? Number(match.entry_fee) : null;

  // وزن‌کشی (هر دو نام را پوشش بده)
  const weighDateRaw =
    match?.weigh_date_jalali ??
    match?.weigh_in_date_jalali ??
    match?.weigh_date ??
    match?.weigh_in_date ??
    null;

  return (
    <div className="match-card" dir="rtl">
      <img
        src={imageSrc}
        alt="پوستر مسابقه"
        className="match-image"
        onError={(e) => (e.currentTarget.src = "/placeholder.jpg")}
      />

      <h3 className="match-title">{title}</h3>

      <div className="match-details">
        <p>سبک مسابقه: {match?.style_display || "—"}</p>

        {/* گروه سنی: فقط پومسه */}
        {!ky && <p>گروه سنی: {ageText}</p>}

        <p>رده کمربندی: {beltText}</p>
        <p>جنسیت: {match?.gender_display || "—"}</p>

        <p>
          شروع ثبت‌نام:{" "}
          {fmtDateFa(
            match?.registration_start_jalali ?? match?.registration_start
          )}
        </p>
        <p>
          پایان ثبت‌نام:{" "}
          {fmtDateFa(
            match?.registration_end_jalali ?? match?.registration_end
          )}
        </p>

        {/* وزن‌کشی فقط در کیوروگی */}
        {ky && <p>تاریخ وزن‌کشی: {fmtDateFa(weighDateRaw)}</p>}

        {/* قرعه‌کشی اگر مقدار دارد */}
        {drawDate ? <p>تاریخ قرعه‌کشی: {fmtDateFa(drawDate)}</p> : null}

        <p>
          تاریخ برگزاری:{" "}
          {fmtDateFa(
            match?.competition_date_jalali ??
              match?.competition_date ??
              match?.start_date
          )}
        </p>

        <p>
          مبلغ ورودی:{" "}
          {fee != null
            ? fee > 0
              ? `${toPersianDigits(fee.toLocaleString())} ریال`
              : "رایگان"
            : "—"}
        </p>

        <p>محل برگزاری: {city || "—"}</p>
      </div>

      {onDetailsClick ? (
        <button className="match-button" onClick={() => onDetailsClick(match)}>
          جزئیات بیشتر و ثبت نام
        </button>
      ) : slug ? (
        <Link
          className="match-button"
          to={`/dashboard/${encodeURIComponent(
            role
          )}/competitions/${encodeURIComponent(slug)}`}
        >
          جزئیات بیشتر و ثبت نام
        </Link>
      ) : (
        <button className="match-button" disabled title="شناسه عمومی موجود نیست">
          جزئیات بیشتر و ثبت نام
        </button>
      )}
    </div>
  );
};

export default MatchCard;
