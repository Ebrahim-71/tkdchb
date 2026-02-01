import React from "react";
import { Link } from "react-router-dom";
import "./SeminarCard.css";

const toPersianDigits = (str) => String(str ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const fmtDateFa = (val, faVal) => {
  const base = faVal || (val ? String(val).slice(0, 10).replace(/-/g, "/") : "");
  return base ? toPersianDigits(base) : "—";
};

function getRole() {
  return localStorage.getItem("user_role") || "player";
}

const SeminarCard = ({ seminar }) => {
  const role = getRole();
  const slug = seminar?.public_id;
  const imageSrc = seminar?.poster_url || "/placeholder.jpg";

  return (
    <div className="seminar-card">
      <img
        src={imageSrc}
        alt="پوستر سمینار"
        className="seminar-image"
        onError={(e) => (e.currentTarget.src = "/placeholder.jpg")}
      />

      <h3 className="seminar-title">{seminar?.title || "—"}</h3>

      <div className="seminar-details">
        <p>محل برگزاری: {seminar?.location || "—"}</p>
        <p>
          هزینه:{" "}
          {seminar?.fee
            ? `${toPersianDigits(Number(seminar.fee).toLocaleString())} تومان`
            : "رایگان"}
        </p>
        <p>شروع ثبت‌نام: {fmtDateFa(seminar?.registration_start, seminar?.registration_start_jalali)}</p>
        <p>پایان ثبت‌نام: {fmtDateFa(seminar?.registration_end, seminar?.registration_end_jalali)}</p>
        <p>تاریخ برگزاری: {fmtDateFa(seminar?.event_date, seminar?.event_date_jalali)}</p>
      </div>

      {slug ? (
        <Link
          className="seminar-button"
          to={`/dashboard/${encodeURIComponent(role)}/courses/${encodeURIComponent(slug)}`}
        >
          جزئیات بیشتر و ثبت نام
        </Link>
      ) : (
        <button className="seminar-button" disabled title="شناسه عمومی موجود نیست">
          جزئیات بیشتر و ثبت نام
        </button>
      )}
    </div>
  );
};

export default SeminarCard;
