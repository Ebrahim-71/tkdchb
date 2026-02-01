// src/components/seminar/SeminarDetail.jsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import "./SeminarDetail.css";

const API_BASE = process.env.REACT_APP_API_BASE_URL || "https://api.chbtkd.ir";

const toFaDigits = (s) => String(s ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const fmtDateFa = (gDate, faStr) => {
  const base = faStr || (gDate ? String(gDate).slice(0, 10).replace(/-/g, "/") : "");
  return base ? toFaDigits(base) : "—";
};
const roleArrayFromRole = (role) => {
  if (role === "both") return ["coach", "referee"];
  if (["player", "coach", "referee"].includes(role)) return [role];
  return [];
};

// خواندن امن از چند کلید احتمالی (ساپورت مسیرهای تو در تو)
const pickFirst = (obj, keys, fallback = "—") => {
  if (!obj) return fallback;
  for (const k of keys) {
    const val = k.includes(".")
      ? k.split(".").reduce((acc, part) => (acc ? acc[part] : undefined), obj)
      : obj?.[k];
    if (val !== undefined && val !== null && String(val).trim() !== "") return String(val);
  }
  return fallback;
};

const SeminarDetail = () => {
  const navigate = useNavigate();
  const { slug } = useParams();
  const role = (localStorage.getItem("user_role") || "player").toLowerCase();
  const token =
    localStorage.getItem(`${role}_token`) ||
    localStorage.getItem("access_token") ||
    "";

  const [seminar, setSeminar] = useState(null);
  const [profile, setProfile] = useState(null);         // پروفایل داشبورد
  const [miniProfile, setMiniProfile] = useState(null); // پروفایل مینیمال (کدملی/کمربند)
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const [showConfirm, setShowConfirm] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);

  const canRegisterByRole = useMemo(() => {
    if (!seminar) return false;
    if (["club", "heyat", "board"].includes(role)) return false;
    const allowed = seminar.allowed_roles || [];
    if (!allowed.length) return true;
    const req = roleArrayFromRole(role);
    return req.some((r) => allowed.includes(r));
  }, [seminar, role]);

  const statusBadge = useMemo(() => {
    if (!seminar) return null;
    const today = new Date().toISOString().slice(0, 10);
    const open =
      (seminar.registration_start && seminar.registration_start <= today) &&
      (seminar.registration_end && seminar.registration_end >= today);
    const upcoming = seminar.event_date && seminar.event_date >= today;
    if (open) return { text: "در حال ثبت‌نام", type: "open" };
    if (upcoming) return { text: "رویداد آینده", type: "upcoming" };
    return { text: "پایان‌یافته", type: "past" };
  }, [seminar]);

  // 1) دریافت جزئیات سمینار + پروفایل داشبورد
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        setLoading(true);
        setErr("");
        const semReq = axios.get(`${API_BASE}/api/competitions/seminars/${encodeURIComponent(slug)}/`);
        const profReq = token
          ? axios.get(`${API_BASE}/api/auth/dashboard/${encodeURIComponent(role)}/`, {
              headers: { Authorization: `Bearer ${token}` },
            })
          : Promise.resolve({ data: null });

        const [semRes, profRes] = await Promise.all([semReq, profReq]);
        if (cancel) return;
        setSeminar(semRes.data || null);
        setProfile(profRes.data || null);
      } catch {
        if (!cancel) setErr("خطا در دریافت اطلاعات سمینار");
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, [slug, role, token]);

  // 2) گرفتن mini-profile (اولویت با این برای کدملی/کمربند)
  useEffect(() => {
    if (!token) return;
    let cancel = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/api/auth/profile/mini/`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!cancel) setMiniProfile(data || {});
      } catch {
        // اگر نبود/خطا داد، ایرادی ندارد
      }
    })();
    return () => { cancel = true; };
  }, [token]);

  const onBack = () => {
    navigate(`/dashboard/${encodeURIComponent(role)}?section=courses`);
  };

  const onClickRegister = () => {
    setShowConfirm(true);
    setSuccessMsg("");
    if (!token) setErr("برای ثبت‌نام باید وارد حساب شوید.");
  };

  const onConfirmAndPay = async () => {
    if (!seminar || !token) {
      setErr("برای ثبت‌نام باید وارد شوید.");
      return;
    }
    const roles = roleArrayFromRole(role);
    if (roles.length === 0) {
      setErr("این نقش امکان ثبت‌نام در سمینار را ندارد.");
      return;
    }

    setRegistering(true);
    setErr("");
    setSuccessMsg("");
    try {
      const { data } = await axios.post(
        `${API_BASE}/api/competitions/auth/seminars/${encodeURIComponent(slug)}/register/`,
        { roles },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      // ======== پرداخت (فعلاً غیرفعال) ========
      // وقتی بک‌اند payment_url برگردوند، فقط این 3 خط رو از کامنت دربیار:
      // if (data?.payment_required && data?.payment_url) {
      //   window.location.href = data.payment_url;
      //   return;
      // }
      // =======================================

      // رفتار فعلی: صرفاً ثبت‌نام
      if (data?.status === "ok") {
        setSuccessMsg("ثبت‌نام شما با موفقیت انجام شد.");
        setAlreadyRegistered(true);
        setShowConfirm(false);
        return;
      }

      setSuccessMsg("درخواست ثبت‌نام ارسال شد.");
      setAlreadyRegistered(true);
      setShowConfirm(false);
    } catch (e) {
      const code = e?.response?.status;
      const detail = e?.response?.data?.detail || "";
      if (code === 400 || code === 409) {
        if ((detail + "").toLowerCase().includes("unique") || (detail + "").includes("exists")) {
          setAlreadyRegistered(true);
          setErr("شما قبلاً در این سمینار ثبت‌نام کرده‌اید.");
        } else {
          setErr(detail || "ثبت‌نام ممکن نشد.");
        }
      } else if (code === 401) {
        setErr("لطفاً دوباره وارد شوید.");
      } else {
        setErr("خطا در ثبت‌نام. لطفاً دوباره تلاش کنید.");
      }
    } finally {
      setRegistering(false);
    }
  };

  if (loading) return <div className="seminar-detail"><p>در حال بارگذاری…</p></div>;
  if (err && !seminar) return <div className="seminar-detail"><p className="sd-error">{err}</p></div>;
  if (!seminar) return null;

  const imageSrc = seminar.poster_url || "/placeholder.jpg";

  // نام: اول mini، بعد dashboard
  const fullName =
    (pickFirst(miniProfile, ["full_name","name"], "") ||
     `${pickFirst(miniProfile, ["first_name"], "")} ${pickFirst(miniProfile, ["last_name"], "")}`.trim()) ||
    (pickFirst(profile, ["full_name","name"], "") ||
     `${pickFirst(profile, ["first_name"], "")} ${pickFirst(profile, ["last_name"], "")}`.trim()) ||
    "—";

  // کدملی: اول mini، بعد dashboard (پوشش کلیدهای مرسوم)
  const nationalCodeRaw =
    pickFirst(miniProfile, [
      "national_code","nationalCode","nationalcode",
      "national_id","nationalId","melli_code","melliCode"
    ], "") ||
    pickFirst(profile, [
      "national_code","nationalCode","user.national_code","profile.national_code",
      "nid","national_id","nationalId","national_number","nationalNumber"
    ], "");
  const nationalCode = nationalCodeRaw ? toFaDigits(nationalCodeRaw) : "—";

  // کمربند: اول mini، بعد dashboard
  const beltTitleRaw =
    pickFirst(miniProfile, [
      "belt_grade","beltGrade","belt_title","beltTitle","belt_name","beltName","rank_title","rank"
    ], "") ||
    pickFirst(profile, [
      "belt_grade","beltGrade","belt_title","beltTitle","belt_name","beltName",
      "rank_title","rank","belt_group_label","beltGroupLabel","belt_group.label","belt.label"
    ], "");
  const beltTitle = beltTitleRaw || "—";

  const canClickRegister = canRegisterByRole && !alreadyRegistered;
  const finalCtaLabel = seminar?.fee ? "تایید و پرداخت" : "تایید ثبت‌نام";

  return (
    <div className="seminar-detail" dir="rtl">
      <div className="sd-head">
        <button className="sd-back" onClick={onBack} aria-label="بازگشت">
          <span className="sd-back-icon">↩</span> بازگشت به دوره‌های آموزشی
        </button>

        <div className="sd-badges">
          {statusBadge && <span className={`sd-badge sd-${statusBadge.type}`}>{statusBadge.text}</span>}
          {alreadyRegistered && <span className="sd-badge sd-ok">ثبت‌نام‌شده</span>}
        </div>
      </div>

      <div className="sd-card">
        <div className="sd-media">
          <img
            src={imageSrc}
            alt="پوستر سمینار"
            className="sd-image"
            onError={(e) => (e.currentTarget.src = "/placeholder.jpg")}
          />
        </div>

        <div className="sd-body">
          <h1 className="sd-title">{seminar?.title || "—"}</h1>

          <div className="sd-meta">
            <div className="sd-meta-item">
              <span className="sd-meta-icon">📍</span>
              <div className="sd-meta-text">
                <span className="sd-meta-label">محل برگزاری</span>
                <span className="sd-meta-value">{seminar?.location || "—"}</span>
              </div>
            </div>

            <div className="sd-meta-item">
              <span className="sd-meta-icon">💳</span>
              <div className="sd-meta-text">
                <span className="sd-meta-label">هزینه</span>
                <span className="sd-meta-value">
                  {seminar?.fee ? `${toFaDigits(Number(seminar.fee).toLocaleString())} تومان` : "رایگان"}
                </span>
              </div>
            </div>

            <div className="sd-meta-item">
              <span className="sd-meta-icon">🟢</span>
              <div className="sd-meta-text">
                <span className="sd-meta-label">شروع ثبت‌نام</span>
                <span className="sd-meta-value">
                  {fmtDateFa(seminar?.registration_start, seminar?.registration_start_jalali)}
                </span>
              </div>
            </div>

            <div className="sd-meta-item">
              <span className="sd-meta-icon">🔴</span>
              <div className="sd-meta-text">
                <span className="sd-meta-label">پایان ثبت‌نام</span>
                <span className="sd-meta-value">
                  {fmtDateFa(seminar?.registration_end, seminar?.registration_end_jalali)}
                </span>
              </div>
            </div>

            <div className="sd-meta-item">
              <span className="sd-meta-icon">📅</span>
              <div className="sd-meta-text">
                <span className="sd-meta-label">تاریخ برگزاری</span>
                <span className="sd-meta-value">
                  {fmtDateFa(seminar?.event_date, seminar?.event_date_jalali)}
                </span>
              </div>
            </div>
          </div>

          {seminar?.description && <div className="sd-desc">{seminar.description}</div>}

          {err && <p className="sd-error">{err}</p>}
          {successMsg && <p className="sd-success">{successMsg}</p>}

          {!alreadyRegistered && (
            <>
              {!showConfirm ? (
                <button
                  className="sd-primary"
                  onClick={onClickRegister}
                  disabled={!canClickRegister}
                  title={!canRegisterByRole ? "نقش شما مجاز به ثبت‌نام نیست" : ""}
                >
                  ثبت نام
                </button>
              ) : (
                <>
                  <div className="sd-confirm">
                    <div className="sd-field">
                      <label>نام و نام خانوادگی</label>
                      <input type="text" value={fullName} disabled />
                    </div>
                    <div className="sd-field">
                      <label>درجه کمربند</label>
                      <input type="text" value={beltTitle} disabled />
                    </div>
                    <div className="sd-field">
                      <label>کد ملی</label>
                      <input type="text" value={nationalCode} disabled />
                    </div>
                  </div>

                  <button className="sd-primary" onClick={onConfirmAndPay} disabled={registering}>
                    {registering ? "در حال ارسال…" : finalCtaLabel}
                  </button>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SeminarDetail;
