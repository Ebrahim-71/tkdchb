// src/components/Login/competitions/EnrollmentCard.jsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getEnrollmentDetail,
  getEnrollmentCard,
  getEnrollmentCardUrl,
  API_BASE,
} from "../../../api/competitions";
import "./EnrollmentCard.css";

/* ---------- helpers ---------- */
const toFa = (s = "") => String(s).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const absUrl = (u) => (u ? (u.startsWith?.("http") ? u : `${API_BASE}${u}`) : null);


const pick = (o, ...keys) => keys.map((k) => o?.[k]).find((v) => v != null);

/* ================================= */
export default function EnrollmentCard() {
  const { role, enrollmentId } = useParams();
  const navigate = useNavigate();

  const [enroll, setEnroll] = useState(null); // JSON جزئیات ثبت‌نام
  const [cardUrl, setCardUrl] = useState(null); // URL تصویر کارت (اگر موجود)
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;

    (async () => {
      setLoading(true);
      setErr("");
      setEnroll(null);
      setCardUrl(null);

      // ✅ یک متغیر لوکال برای جلوگیری از stale-state
      let localCardUrl = null;

      try {
        // 1) اول دیتیل را می‌گیریم تا kind را درست تشخیص دهیم
        const detail = await getEnrollmentDetail(enrollmentId);
        if (!alive) return;

        setEnroll(detail);

        const inferredKind = (() => {
          const kind = String(
            detail?.kind ||
            detail?.discipline ||
            detail?.style ||
            detail?.competition_kind ||
            detail?.competition_style ||
            detail?.competition_type ||
            ""
          ).toLowerCase();

          // هر چیزی که بوی poomsae بدهد
          if (kind.includes("poom") || kind.includes("پومسه")) return "poomsae";
          return "kyorugi";
        })();

        // 2) حالا کارت را با kind درست می‌گیریم
        try {
          const cardRes = await getEnrollmentCard(enrollmentId, { kind: inferredKind });
          if (!alive) return;

          const fromJson = getEnrollmentCardUrl(cardRes);
          if (fromJson) localCardUrl = absUrl(fromJson);

          if (!fromJson && typeof cardRes === "string") {
            localCardUrl = absUrl(cardRes);
          }

          // اگر خود cardRes شیء بود، می‌تواند داده‌های کارت/ثبت‌نام را داشته باشد
          if (cardRes && typeof cardRes === "object" && !Array.isArray(cardRes)) {
            setEnroll((prev) => prev ?? cardRes);
          }

          if (localCardUrl) setCardUrl(localCardUrl);
        } catch (eCard) {
          // اگر کارت پیدا نشد/مجاز نبود، خطا را غیر از 404 نشان بده
          if (eCard?.status !== 404 && eCard?.status !== 403) {
            if (alive) setErr(eCard?.message || "خطا در دریافت کارت");
          }
        }

        // 3) اگر از detail توانستیم URL کارت را استخراج کنیم و هنوز نداریم
        const urlFromDetail =
          getEnrollmentCardUrl(detail) ||
          pick(detail, "card_url", "cardUrl", "card") ||
          detail?.card?.url;

        if (!localCardUrl && urlFromDetail) {
          localCardUrl = absUrl(String(urlFromDetail));
          if (localCardUrl) setCardUrl(localCardUrl);
        }

      } catch (eDetail) {
        if (!alive) return;
        setErr(eDetail?.message || "کارت/ثبت‌نام یافت نشد");
      } finally {
        if (alive) setLoading(false);
      }
    })();

    return () => {
      alive = false;
    };
  }, [enrollmentId]);


  const status = useMemo(
    () =>
      String(enroll?.status || enroll?.payment_status || "").toLowerCase(),
    [enroll]
  );
  const isPaidLike = ["paid", "confirmed", "approved", "accepted", "completed"].includes(
    status
  );

  // ✅ تشخیص پومسه (خیلی هجومی‌تر)
  const isPoomsae = useMemo(() => {
    if (!enroll) return false;

    const pt = String(enroll.poomsae_type || "").toLowerCase();
    const ptd = String(enroll.poomsae_type_display || "").toLowerCase();
    const ageName =
      enroll.age_category_name ||
      enroll.age_category_label ||
      enroll.age_category_title ||
      "";

    // اگر خود فیلدهای مخصوص پومسه هستند
    if (pt || ptd || ageName) return true;

    // اگر نوع مسابقه/دیسکپلین مشخص است
    const kind = String(
      enroll.kind || enroll.discipline || enroll.style || ""
    ).toLowerCase();
    if (
      kind === "poomsae" ||
      kind.includes("poom") ||
      kind.includes("پومسه")
    )
      return true;

    const compStyle = String(
      enroll.competition_style ||
        enroll.competition_kind ||
        enroll.competition_type ||
        ""
    ).toLowerCase();
    if (
      compStyle === "poomsae" ||
      compStyle.includes("poom") ||
      compStyle.includes("پومسه")
    )
      return true;

    // اگر عملاً وزن نداریم ولی گروه سنی داریم → احتمالاً پومسه است
    const hasWeightField =
      "declared_weight" in enroll || "weight_name" in enroll;
    const hasWeightValue =
      enroll.declared_weight || (enroll.weight_name && enroll.weight_name !== "—");

    if (!hasWeightValue && ageName && !hasWeightField) return true;

    return false;
  }, [enroll]);

  /* ---------- UI states ---------- */
  if (loading) {
    return (
      <div className="cd-container">
        <div className="cd-skeleton">در حال بارگذاری…</div>
      </div>
    );
  }
  if (err) {
    return (
      <div className="cd-container">
        <div className="cd-error">{err}</div>
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-light" onClick={() => navigate(-1)}>
            بازگشت
          </button>
        </div>
      </div>
    );
  }
  if (!enroll && !cardUrl) {
    return (
      <div className="cd-container">
        <div className="cd-error">کارت یافت نشد.</div>
      </div>
    );
  }

  /* ---------- fields ---------- */
  const {
    competition_title,
    competition_date_jalali,
    first_name,
    last_name,
    birth_date,
    photo,
    declared_weight,
    weight_name,
    belt,
    belt_group,
    insurance_number,
    insurance_issue_date_jalali,
    coach_name,
    club_name,
    // پومسه
    poomsae_type,
    poomsae_type_display,
    age_category_name,
    age_category_label,
    age_category_title,
  } = enroll || {};

  const fullName = [first_name, last_name].filter(Boolean).join(" ");
  const photoUrl = absUrl(photo);

  const ageValue =
    age_category_name || age_category_label || age_category_title || "—";

  // ✅ لیبل‌ها برای کیوروگی / پومسه
  const leftTopLabel = isPoomsae ? " سبک مسابقه انفرادی " : "وزن اعلامی";
  const rightBottomLabel = isPoomsae ? "گروه سنی" : "رده وزنی";

  // مقدار سبک پومسه
  const poomsaeStyleValue =
    poomsae_type_display ||
    (poomsae_type === "creative"
      ? "ابداعی"
      : poomsae_type === "standard"
      ? "استاندارد"
      : poomsae_type || "—");

  const leftTopValue = isPoomsae
    ? poomsaeStyleValue
    : declared_weight
    ? `${toFa(declared_weight)} کیلوگرم`
    : "—";

  const rightBottomValue = isPoomsae ? ageValue : weight_name || "—";

  return (
    <div className="cd-container" dir="rtl" style={{ maxWidth: 900 }}>
      <div className="enroll-card enroll-card--outlined">
        <div className="enroll-card__head enroll-card__head--center">
          <h2 className="enroll-card__title">کارت شناسایی بازیکن</h2>
        </div>

        {enroll && (
          <>
            <div className="enroll-card__grid" style={{ marginTop: 12 }}>
              <Info
                label="عنوان مسابقه"
                value={competition_title || "—"}
              />
              <Info
                label="تاریخ برگزاری"
                value={competition_date_jalali || "—"}
              />
            </div>

            <div className="enroll-card__divider" />

            <div className="enroll-card__grid enroll-card__grid--photo">
              <div className="enroll-card__photo-wrap">
                {photoUrl ? (
                  <img
                    className="enroll-card__photo"
                    src={photoUrl}
                    alt="player"
                  />
                ) : (
                  <div className="enroll-card__photo placeholder">
                    بدون عکس
                  </div>
                )}
              </div>

              <div className="enroll-card__info-cols">
                <Info
                  label="نام و نام خانوادگی"
                  value={fullName || "—"}
                />
                <Info label="تاریخ تولد" value={birth_date || "—"} />
                <Info label="کمربند" value={belt || "—"} />
                <Info
                  label="گروه کمربندی"
                  value={belt_group || "—"}
                />
                <Info label={rightBottomLabel} value={rightBottomValue} />
              </div>

              <div className="enroll-card__info-cols">
                <Info label={leftTopLabel} value={leftTopValue} />
                <Info label="نام مربی" value={coach_name || "—"} />
                <Info label="نام باشگاه" value={club_name || "—"} />
                <Info
                  label="شماره بیمه"
                  value={insurance_number || "—"}
                />
                <Info
                  label="تاریخ صدور بیمه"
                  value={insurance_issue_date_jalali || "—"}
                />
              </div>
            </div>
          </>
        )}

        <div className="enroll-card__footer">
          <div className="enroll-card__notice">
            این کارت را چاپ کرده و روز مسابقه همراه خود داشته باشید.
          </div>
          <div className="cd-actions enroll-card__actions">
            <button
              className="btn btn-outline"
              onClick={() => window.print()}
            >
              چاپ کارت
            </button>
            <button
              className="btn btn-light"
              onClick={() =>
                navigate(`/dashboard/${encodeURIComponent(role)}`)
              }
            >
              بازگشت به داشبورد
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Info({ label, value }) {
  return (
    <div className="cd-row">
      <div className="cd-label">{label}</div>
      <div className="cd-value">{value}</div>
    </div>
  );
}
