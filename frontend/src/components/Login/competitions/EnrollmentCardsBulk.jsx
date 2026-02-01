// src/components/Login/competitions/EnrollmentCardsBulk.jsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useParams, Link, useLocation } from "react-router-dom";
import { getEnrollmentCard, API_BASE } from "../../../api/competitions";

import "./EnrollmentCard.css";


async function resolveEnrollmentIdsFromPid(pid, kind) {
  const url =
    `${API_BASE}/api/payments/intents/${encodeURIComponent(pid)}/enrollments/` +
    (kind ? `?kind=${encodeURIComponent(kind)}` : "");

  const role = (localStorage.getItem("user_role") || "").toLowerCase().trim();
  const roleTokenKey = role ? `${role}_token` : null;

  const token =
    (roleTokenKey && localStorage.getItem(roleTokenKey)) ||
    localStorage.getItem("coach_token") ||
    localStorage.getItem("both_token") ||
    localStorage.getItem("access_token") ||
    localStorage.getItem("access") ||
    localStorage.getItem("auth_token") ||
    localStorage.getItem("token");


  const res = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "omit",
  });


  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail || data?.error || `HTTP ${res.status}`);

  const arr = Array.isArray(data?.enrollment_ids) ? data.enrollment_ids : [];
  return arr.map(Number).filter((n) => Number.isFinite(n) && n > 0);
}

const toFa = (s = "") => String(s).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
const absUrl = (u) => (u ? (u.startsWith?.("http") ? u : `${API_BASE}${u}`) : null);

const isTeamEnrollment = (data) => {
  // معیار تیمی بودن: اولویت با فیلدهای مطمئن‌تر
  const mode = String(data?.mode || "").toLowerCase();
  if (mode === "team") return true;

  // بک‌اند برای تیمی معمولاً "تیمی ..." می‌دهد
  const ps = String(data?.poomsae_style || "").trim();
  if (ps.startsWith("تیمی")) return true;

  // team_name اگر واقعاً اسم تیم باشد (نه "-" و نه "—")
  const tn = String(data?.team_name || "").trim();
  if (!tn || tn === "-" || tn === "—") return false;

  return true;
};

const getTeamName = (data) => {
  const candidates = [
    data?.team_name,
    data?.teamName,
    data?.team_title,
    data?.teamTitle,
    data?.team,
    data?.team?.name,
    data?.team?.title,
  ];

  const t = candidates
    .map((x) => String(x || "").trim())
    .find((x) => x && x !== "-" && x !== "—");
  return t || "";
};

const getPoomsaeStyleLabel = (data) => {
  // بک‌اند شما معمولاً این را می‌دهد (مثل "تیمی استاندارد" / "تیمی ابداعی")
  // اگر نبود، از type/display خودتان بسازید
  if (data?.poomsae_style) return String(data.poomsae_style);

  const type = String(data?.poomsae_type || "").toLowerCase();
  const typeFa =
    type === "creative" ? "ابداعی" : type === "standard" ? "استاندارد" : "—";
  const sectionFa = isTeamEnrollment(data) ? "تیمی" : "انفرادی";
  return `${sectionFa} ${typeFa}`;
};

const playerKeyOf = (data) => {
  // ✅ اگر بک‌اند national_id / id دارد، حتماً از همان استفاده کن
  const nat = data?.national_id || data?.nationalId || data?.nid;
  if (nat) return `nat:${String(nat)}`;

  // fallback (کم‌ریسک‌ترین ترکیب موجود در کارت)
  const fn = String(data?.first_name || "").trim();
  const ln = String(data?.last_name || "").trim();
  const bd = String(data?.birth_date || "").trim();

  // ❌ team_name را از کلید بازیکن حذف کردیم
  return `p:${fn}|${ln}|${bd}`;
};

const mergeSameSectionCardsPerPlayer = (okItems) => {
  // okItems: [{id, status:'ok', data}]
  const byPlayer = new Map();

  for (const it of okItems) {
    const pk = playerKeyOf(it.data);
    if (!byPlayer.has(pk)) byPlayer.set(pk, []);
    byPlayer.get(pk).push(it);
  }

  const out = [];

  for (const [, itemsOfPlayer] of byPlayer.entries()) {
    const buckets = { team: [], individual: [] };

    for (const it of itemsOfPlayer) {
      const key = isTeamEnrollment(it.data) ? "team" : "individual";
      buckets[key].push(it);
    }

    for (const key of ["team", "individual"]) {
      const arr = buckets[key];
      if (arr.length === 0) continue;

      if (arr.length === 1) {
        out.push(arr[0]);
        continue;
      }

      const base = arr[0];

      const styles = Array.from(
        new Set(arr.map((x) => getPoomsaeStyleLabel(x.data)).filter(Boolean))
      );

      // ✅ اگر تیمی بود، اسم همه تیم‌ها را هم merge کن
      const teamNames = Array.from(
        new Set(arr.map((x) => getTeamName(x?.data)).filter(Boolean))
      );

      out.push({
        ...base,
        data: {
          ...base.data,
          poomsae_style: styles.join(" و "),
          ...(key === "team"
            ? {
                team_names: teamNames, // اختیاری ولی مفید
                team_name: teamNames.length
                  ? teamNames.join(" و ")
                  : getTeamName(base.data) || "—",
              }
            : {}),
        },
        merged_ids: arr.map((x) => x.id),
      });
    }
  }

  return out;
};

function Info({ label, value }) {
  return (
    <div className="cd-row">
      <div className="cd-label">{label}</div>
      <div className="cd-value">{value}</div>
    </div>
  );
}

function CardView({ data }) {
  if (!data) return null;

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
    style,
    poomsae_style,
  } = data;

  const fullName = [first_name, last_name].filter(Boolean).join(" ");
  const styleNorm = (style || "").toLowerCase();
  const isPoomsae = styleNorm === "poomsae" || styleNorm === "پومسه";

  const categoryLabel = isPoomsae ? "سبک مسابقه" : "رده وزنی";
  const categoryValue = isPoomsae ? poomsae_style || "—" : weight_name || "—";

  return (
    <div className="enroll-card enroll-card--outlined" style={{ marginBottom: 24 }}>
      <div className="enroll-card__head enroll-card__head--center">
        <h2 className="enroll-card__title">کارت شناسایی بازیکن</h2>
      </div>

      <div className="enroll-card__grid">
        <Info label="عنوان مسابقه" value={competition_title || "—"} />
        <Info label="تاریخ برگزاری" value={competition_date_jalali || "—"} />
      </div>

      <div className="enroll-card__divider" />

      <div className="enroll-card__grid enroll-card__grid--photo">
        <div className="enroll-card__photo-wrap">
          {photo ? (
            <img className="enroll-card__photo" src={absUrl(photo)} alt="player" />
          ) : (
            <div className="enroll-card__photo placeholder">بدون عکس</div>
          )}
        </div>

        <div className="enroll-card__info-cols">
          <Info label="نام و نام خانوادگی" value={fullName || "—"} />
          <Info label="تاریخ تولد" value={birth_date || "—"} />
          <Info label="کمربند" value={belt || "—"} />
          <Info label="گروه کمربندی" value={belt_group || "—"} />
          <Info label={categoryLabel} value={categoryValue} />
        </div>

        <div className="enroll-card__info-cols">
          {!isPoomsae && (
            <Info
              label="وزن اعلامی"
              value={declared_weight ? `${toFa(declared_weight)} kg` : "—"}
            />
          )}

          {isPoomsae && isTeamEnrollment(data) && (
            <Info
              label="نام تیم"
              value={
                (Array.isArray(data.team_names) && data.team_names.length
                  ? data.team_names.join(" و ")
                  : data.team_name) || "—"
              }
            />
          )}

          <Info label="نام مربی" value={coach_name || "—"} />
          <Info label="نام باشگاه" value={club_name || "—"} />
          <Info label="شماره بیمه" value={insurance_number || "—"} />
          <Info label="تاریخ صدور بیمه" value={insurance_issue_date_jalali || "—"} />
        </div>
      </div>
    </div>
  );
}

function PendingCard({ id, message }) {
  return (
    <div
      className="cd-card"
      style={{
        marginBottom: 12,
        padding: 12,
        border: "1px dashed #d0d0d0",
        background: "#fafafa",
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>
        کارت ثبت‌نام #{toFa(id)}
      </div>
      <div className="cd-muted">
        {message || "این ثبت‌نام هنوز پرداخت/تأیید نهایی نشده است."}
      </div>
    </div>
  );
}

function ErrorCard({ id, message }) {
  return (
    <div
      className="cd-card"
      style={{
        marginBottom: 12,
        padding: 12,
        border: "1px solid #f3c2c2",
        background: "#fff7f7",
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>خطا برای #{toFa(id)}</div>
      <div className="cd-error" style={{ margin: 0 }}>
        {message || "خطا"}
      </div>
    </div>
  );
}

export default function EnrollmentCardsBulk() {
  const { role } = useParams();

  const roleSafe = useMemo(() => {
    const r =
      (role && String(role).trim()) ||
      (localStorage.getItem("user_role") || "coach");
    return encodeURIComponent(String(r).toLowerCase());
  }, [role]);
  const [sp] = useSearchParams();
  const location = useLocation();

  const idsStr = sp.get("ids") || "";
  const pid = sp.get("pid") || ""; // NEW

  // اگر ids در state آمده بود هم پشتیبانی کن
  const stateIds = location?.state?.ids;
  const rawKind = location?.state?.kind || sp.get("kind") || "kyorugi";


  const kind = ["poomsae", "kyorugi"].includes(String(rawKind).toLowerCase())
    ? String(rawKind).toLowerCase()
    : "kyorugi";

  const ids = useMemo(() => {
    // 1) اول از querystring ids
    const fromQs = idsStr
      .split(",")
      .map((x) => parseInt(String(x).trim(), 10))
      .filter((n) => Number.isFinite(n) && n > 0);

    if (fromQs.length) return fromQs;

    // 2) fallback: ids از state (اگر navigate با state انجام شد)
    if (Array.isArray(stateIds) && stateIds.length) {
      return stateIds.map(Number).filter((n) => Number.isFinite(n) && n > 0);
    }

    return [];
  }, [idsStr, stateIds]);


  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [items, setItems] = useState([]); // [{id, status, data?, message?}]

  // جلوگیری از دوبار اجرا در React StrictMode (dev)
  const runKeyRef = useRef("");

  useEffect(() => {
    let alive = true;

    const runKey = `ids:${idsStr}|pid:${pid}|state:${Array.isArray(stateIds) ? stateIds.join(",") : ""}|kind:${kind}`;
    if (runKeyRef.current === runKey) {
      return () => {
        alive = false;
      };
    }
    runKeyRef.current = runKey;


    const run = async () => {
      try {
        setLoading(true);
        setErr("");

        let idsToLoad = ids;

        // ✅ اگر ids نداریم ولی pid داریم، از endpoint کمکی ids را بگیر
        if ((!idsToLoad || idsToLoad.length === 0) && pid) {
          try {
            idsToLoad = await resolveEnrollmentIdsFromPid(pid, kind);
          } catch (e) {
            setErr(e?.message || "عدم دریافت enrollment_ids از pid");
            idsToLoad = [];
          }
        }

        if (!idsToLoad || idsToLoad.length === 0) {
          if (alive) {
            setItems([]);
            // پیام واضح‌تر
            setErr(
              pid
                ? "هیچ ثبت‌نامی برای این پرداخت پیدا نشد (enrollment_ids خالی است)."
                : "شناسه ثبت‌نام‌ها (ids) در آدرس وجود ندارد."
            );
          }
          return;
        }

        const out = [];

        for (const id of idsToLoad) {
          try {
            const c = await getEnrollmentCard(id, { kind }); // kind = 'kyorugi' یا 'poomsae'

            out.push({ id, status: "ok", data: c });
          } catch (e) {
            const msg = e?.message || "خطا";
            const status = e?.status;

            const isPendingPayment =
              (status === 403 || status === 409 || status === 400) &&
              /پرداخت|تأیید|نهایی|pending/i.test(String(msg || ""));


            if (isPendingPayment) {
              out.push({ id, status: "pending", message: msg });
            } else {
              out.push({ id, status: "error", message: msg });
            }
          }
        }

        if (alive) setItems(out);
      } catch (e) {
        if (alive) setErr(e?.message || "خطا");
      } finally {
        if (alive) setLoading(false);
      }
    };


    run();
    return () => {
      alive = false;
    };
  }, [idsStr, pid, kind, ids]);


  const okCards = items.filter((x) => x.status === "ok");
  const pendingCards = items.filter((x) => x.status === "pending");
  const errorCards = items.filter((x) => x.status === "error");

  const mergedOkCards = useMemo(
    () => mergeSameSectionCardsPerPlayer(okCards),
    [okCards]
  );

  if (loading && items.length === 0) {
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
      </div>
    );
  }

  return (
    <div className="cd-container" dir="rtl" style={{ maxWidth: 900 }}>
      <div className="cd-actions" style={{ marginBottom: 12, gap: 8 }}>
        <button
          className="btn btn-outline"
          onClick={() => window.print()}
          disabled={mergedOkCards.length === 0}
          title={mergedOkCards.length === 0 ? "هیچ کارت آماده‌ای برای چاپ وجود ندارد" : ""}
        >
          چاپ همه کارت‌های آماده
        </button>

        <Link className="btn btn-light" to={`/dashboard/${roleSafe}`}>
          بازگشت
        </Link>


      </div>

      {(pendingCards.length > 0 || errorCards.length > 0) && (
        <div className="cd-note" style={{ marginBottom: 12 }}>
          <div>
            کارت‌های آماده: <strong>{toFa(mergedOkCards.length)}</strong> | در انتظار
            پرداخت/تأیید: <strong>{toFa(pendingCards.length)}</strong> | خطادار:{" "}
            <strong>{toFa(errorCards.length)}</strong>
          </div>
          {pendingCards.length > 0 && (
            <div className="cd-muted" style={{ marginTop: 6 }}>
              اگر پرداخت را انجام دهید (یا مسابقه رایگان باشد و توسط سیستم تأیید شود)،
              کارت‌ها قابل چاپ می‌شوند.
            </div>
          )}
        </div>
      )}

      {items.length === 0 ? (
        <div className="cd-muted">هیچ آیتمی یافت نشد.</div>
      ) : (
        <>
          {/* اول pending ها */}
          {pendingCards.map((x) => (
            <PendingCard key={`p-${x.id}`} id={x.id} message={x.message} />
          ))}

          {/* بعد error ها */}
          {errorCards.map((x) => (
            <ErrorCard key={`e-${x.id}`} id={x.id} message={x.message} />
          ))}

          {/* آخر کارت‌های آماده */}
          {mergedOkCards.map((x, i) => (
            <CardView key={`ok-${x.id}-${i}`} data={x.data} />
          ))}
        </>
      )}
    </div>
  );
}
