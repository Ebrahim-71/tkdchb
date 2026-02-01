// src/components/Login/competitions/PoomsaeTeamRegister.jsx
import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getEligibleStudentsForCoach, API_BASE, registerPoomsaeTeams } from "../../../api/competitions";

import "./PoomsaeTeamRegister.css";

import DatePicker from "react-multi-date-picker";
import persian from "react-date-object/calendars/persian";
import persian_fa from "react-date-object/locales/persian_fa";

/* ---------- Helpers ---------- */

const toFa = (str) => String(str ?? "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);

const normalizeDigits = (s = "") =>
  String(s)
    .replace(/[۰-۹]/g, (d) => "0123456789"["۰۱۲۳۴۵۶۷۸۹".indexOf(d)])
    .replace(/[٠-٩]/g, (d) => "0123456789"["٠١٢٣٤٥٦٧٨٩".indexOf(d)]);

const stripRtlMarks = (s = "") => s.replace(/[\u200e\u200f\u200c\u202a-\u202e]/g, "");

const getId = (s) => s?.id ?? s?.player_id ?? s?.user_id ?? s?.profile_id;

/* ---------- Token ---------- */
const getAuthToken = () => {
  const role = (localStorage.getItem("user_role") || "").toLowerCase().trim();
  const roleTokenKey = role ? `${role}_token` : null;
  const keys = [
    roleTokenKey,
    "coach_token",
    "both_token",
    "access_token",
    "token",
    "access",
    "auth_token",
  ].filter(Boolean);

  for (const k of keys) {
    const v = localStorage.getItem(k);
    if (v) return v;
  }
  return null;
};

/* ---------- Payments ---------- */

async function createPaymentIntent({
  competitionPublicId,
  amount,
  description,
  style = "poomsae_team",
}) {
  const token = getAuthToken();
  if (!token) throw new Error("توکن ورود یافت نشد. لطفاً دوباره وارد شوید.");
  if (!competitionPublicId) throw new Error("شناسه مسابقه برای پرداخت یافت نشد.");

  const url = `${API_BASE}/api/payments/intent/`;

  const payload = {
    competition_public_id: competitionPublicId,
    style: style || "poomsae_team",
    amount,
    description: description || "",
    gateway: "sadad",
  };

  let resp;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("عدم امکان ارتباط با سرور پرداخت (network error).");
  }

  let data = null;
  try {
    data = await resp.json();
  } catch {}

  if (!resp.ok) {
    let msg =
      data?.detail ||
      data?.message ||
      data?.error ||
      (resp.status === 404
        ? "سرویس پرداخت برای این مسابقه روی سرور پیدا نشد (404)."
        : `خطای سرور پرداخت (HTTP ${resp.status}).`);
    throw new Error(msg);
  }
  return data || {};
}

async function startPaymentIntent(publicId, { callbackUrl } = {}) {
  const token = getAuthToken();
  if (!token) throw new Error("توکن ورود یافت نشد. لطفاً دوباره وارد شوید.");

  const url = `${API_BASE}/api/payments/start/${publicId}/`;
  const body = { gateway: "sadad" };
  if (callbackUrl) body.callback_url = callbackUrl;

  let resp;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("عدم امکان ارتباط با سرور پرداخت (network error).");
  }

  let data = null;
  try {
    data = await resp.json();
  } catch {}

  if (!resp.ok) {
    let msg =
      data?.detail ||
      data?.message ||
      data?.error ||
      `خطای شروع پرداخت (HTTP ${resp.status}).`;
    throw new Error(msg);
  }

  return data || {};
}

/* ---------- registration window helpers ---------- */

const normalizeIso = (s) => stripRtlMarks(normalizeDigits(String(s || ""))).slice(0, 10);

const isISODate = (s) =>
  typeof s === "string" && /^\d{4}-\d{2}-\d{2}/.test(normalizeIso(s));

const toDateSafe = (s) => {
  if (!isISODate(s)) return null;
  const t = normalizeIso(s);
  const m = t.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  const y = +m[1];
  const mo = +m[2] - 1;
  const d = +m[3];

  // اگر سال کمتر از 1700 باشد یعنی جلالی است → نادیده بگیر
  if (y < 1700) return null;

  return new Date(y, mo, d);
};

const stripTime = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

/* ---------- team structure ---------- */

const SLOTS_BY_TYPE = {
  standard: { main: 3, reserve: 2 },
  creative: { main: 2, reserve: 1 },
};

const createEmptyTeam = (index = 1) => ({
  tmpId: `team-${index}-${Date.now()}`,
  name: "",
  type: "",
  main: [],
  reserve: [],
  // insurance[playerId] = { number: "", date: "YYYY/MM/DD (jalali)", date_iso: "YYYY-MM-DD" }
  insurance: {},
  errors: {},
});

/* =========================================
   Component
   ========================================= */

export default function PoomsaeTeamRegister() {
  const { slug, role } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [competition, setCompetition] = useState(null);
  const [students, setStudents] = useState([]);

  const [teams, setTeams] = useState([createEmptyTeam(1)]);
  const [submitting, setSubmitting] = useState(false);

  /* --- load eligible students + competition --- */
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr("");

    getEligibleStudentsForCoach(slug, "poomsae")
      .then((res) => {
        if (!alive) return;
        const compData = res?.competition || null;
        const list = Array.isArray(res?.students) ? res.students : [];
        setCompetition(compData);
        setStudents(list);
      })
      .catch((e) => alive && setErr(e?.message || "خطا در دریافت لیست شاگردها / اطلاعات مسابقه"))
      .finally(() => alive && setLoading(false));

    return () => {
      alive = false;
    };
  }, [slug]);

  /* --- registrationOpen: اولویت با فلگ‌ها، اگر نبود از بازه تاریخ --- */
  const registrationOpen = useMemo(() => {
    if (!competition) return false;

    const flag =
      competition.registration_open_effective ??
      competition.registration_open ??
      competition.can_register ??
      competition.canRegister;

    if (typeof flag === "boolean") return flag;

    const start =
      toDateSafe(competition.registration_start) ||
      toDateSafe(competition.registration_start_gregorian) ||
      toDateSafe(competition.registration_start_iso);

    const end =
      toDateSafe(competition.registration_end) ||
      toDateSafe(competition.registration_end_gregorian) ||
      toDateSafe(competition.registration_end_iso);

    const today = stripTime(new Date());

    if (start && end) {
      const s = stripTime(start);
      const e = stripTime(end);
      return today >= s && today <= e;
    }

    return true;
  }, [competition]);

  /* --- player options --- */
  const playerOptions = useMemo(
    () =>
      students.map((s) => {
        const id = getId(s);
        const name = `${s.first_name || ""} ${s.last_name || ""}`.trim() || "—";
        const nat = s.national_code || s.national_id || "";
        const belt = s.belt_grade || s.belt || "";
        const age = s.age_category_name || s.age_group_name || "";
        const labelParts = [name];
        if (nat) labelParts.push(`کدملی: ${nat}`);
        if (belt) labelParts.push(`کمربند: ${belt}`);
        if (age) labelParts.push(`رده: ${age}`);
        return {
          id,
          label: labelParts.join(" | "),
          ageKey: s.age_category_key || s.age_category_name || s.age_group_name || "AGE?",
          beltKey: s.belt_grade || s.belt || "BELT?",
        };
      }),
    [students]
  );

  const findPlayer = (pid) => playerOptions.find((p) => String(p.id) === String(pid)) || null;

  /* --- summary & fee --- */
  const entryFee = Number(competition?.entry_fee || 0);

  const summary = useMemo(() => {
    let standardTeams = 0;
    let creativeTeams = 0;
    let totalSlots = 0;

    teams.forEach((t) => {
      if (!t.type) return;
      if (t.type === "standard") standardTeams++;
      if (t.type === "creative") creativeTeams++;

      const allIds = [...(t.main || []), ...(t.reserve || [])].filter(Boolean);
      totalSlots += allIds.length;
    });

    const totalAmount = entryFee * totalSlots;
    return { standardTeams, creativeTeams, totalSlots, totalAmount };
  }, [teams, entryFee]);

  /* ---------- team editing ---------- */

  const updateTeam = (tmpId, patch) => {
    setTeams((prev) => prev.map((t) => (t.tmpId === tmpId ? { ...t, ...patch } : t)));
  };

  const handleTypeChange = (tmpId, newType) => {
    setTeams((prev) =>
      prev.map((t) => {
        if (t.tmpId !== tmpId) return t;
        const slots = SLOTS_BY_TYPE[newType] || { main: 0, reserve: 0 };
        return {
          ...t,
          type: newType,
          main: (t.main || []).slice(0, slots.main).concat(
            Array(Math.max(slots.main - (t.main || []).length, 0)).fill(null)
          ),
          reserve: (t.reserve || []).slice(0, slots.reserve).concat(
            Array(Math.max(slots.reserve - (t.reserve || []).length, 0)).fill(null)
          ),
          errors: { ...t.errors, type: undefined },
        };
      })
    );
  };

  const handleMemberChange = (tmpId, kind, index, value) => {
    setTeams((prev) =>
      prev.map((t) => {
        if (t.tmpId !== tmpId) return t;

        const arr = [...(t[kind] || [])];
        const pid = value ? Number(value) : null;
        arr[index] = pid;

        const insurance = { ...(t.insurance || {}) };
        if (pid && !insurance[String(pid)]) {
          insurance[String(pid)] = { number: "", date: "", date_iso: "" };
        }

        return {
          ...t,
          [kind]: arr,
          insurance,
          errors: { ...t.errors, [`${kind}_${index}`]: undefined },
        };
      })
    );
  };

  const handleInsuranceChange = (tmpId, pid, field, value) => {
    setTeams((prev) =>
      prev.map((t) => {
        if (t.tmpId !== tmpId) return t;
        const insurance = { ...(t.insurance || {}) };
        const key = String(pid);
        insurance[key] = {
          ...(insurance[key] || { number: "", date: "", date_iso: "" }),
          [field]: value,
        };

        return { ...t, insurance };
      })
    );
  };

  const addTeam = () => {
    setTeams((prev) => [...prev, createEmptyTeam(prev.length + 1)]);
  };

  const removeTeam = (tmpId) => {
    setTeams((prev) => (prev.length <= 1 ? prev : prev.filter((t) => t.tmpId !== tmpId)));
  };

  /* ---------- date picker renderer ---------- */

  const renderInsuranceDatePicker = (teamTmpId, pid, value) => (
    <DatePicker
      calendar={persian}
      locale={persian_fa}
      value={value || null}
      format="YYYY/MM/DD"
      inputClass="cd-input"
      calendarPosition="bottom-right"
      onChange={(dateObj) => {
        const jalali = dateObj ? dateObj.format("YYYY/MM/DD") : "";

        let iso = "";
        try {
          const d = dateObj ? dateObj.toDate() : null; // Gregorian Date
          if (d) {
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            iso = `${y}-${m}-${day}`;
          }
        } catch {}

        handleInsuranceChange(teamTmpId, pid, "date", jalali);
        handleInsuranceChange(teamTmpId, pid, "date_iso", iso);
      }}
      disabled={!registrationOpen}
    />
  );

  /* ---------- validation ---------- */

  const validateTeams = () => {
    let hasError = false;
    const newTeams = teams.map((t) => ({ ...t, errors: {} }));
    const usage = {}; // usage[playerId] = { standard, creative }

    newTeams.forEach((t, tIndex) => {
      const errors = {};
      const isStandard = t.type === "standard";
      const isCreative = t.type === "creative";

      if (!t.type) {
        errors.type = "نوع تیم (استاندارد/ابداعی) را انتخاب کنید.";
        hasError = true;
      }

      if (!t.name || !t.name.trim()) {
        errors.name = "نام تیم را وارد کنید.";
        hasError = true;
      }

      const slots = SLOTS_BY_TYPE[t.type] || { main: 0, reserve: 0 };
      const main = t.main || [];
      const reserve = t.reserve || [];

      for (let i = 0; i < slots.main; i++) {
        const pid = main[i];
        if (!pid) {
          errors[`main_${i}`] = "این عضو اصلی الزامی است.";
          hasError = true;
        }
      }

      const allIds = [...main, ...reserve].filter(Boolean);

      // بیمه برای هر بازیکن انتخاب‌شده
      allIds.forEach((pid) => {
        const ins = (t.insurance || {})[String(pid)] || {};
        if (!String(ins.number || "").trim()) {
          errors[`ins_no_${pid}`] = "شماره بیمه برای این بازیکن الزامی است.";
          hasError = true;
        }
        if (!String(ins.date || "").trim()) {
          errors[`ins_date_${pid}`] = "تاریخ صدور بیمه برای این بازیکن الزامی است.";
          hasError = true;
        }
      });

      // سن/کمربند یکسان
      if (allIds.length > 0) {
        let ageKey = null;
        let beltKey = null;
        for (const pid of allIds) {
          const p = findPlayer(pid);
          if (!p) continue;
          if (ageKey == null) ageKey = p.ageKey;
          if (beltKey == null) beltKey = p.beltKey;
          if (ageKey !== p.ageKey) {
            errors.age_mismatch = "رده سنی تمام اعضای تیم باید یکسان باشد.";
            hasError = true;
            break;
          }
          if (beltKey !== p.beltKey) {
            errors.belt_mismatch = "رده کمربندی تمام اعضای تیم باید یکسان باشد.";
            hasError = true;
            break;
          }
        }
      }

      // جلوگیری از چندبار انتخاب در تیم‌های هم‌نوع
      allIds.forEach((pid) => {
        const key = String(pid);
        if (!usage[key]) usage[key] = { standard: 0, creative: 0 };
        if (isStandard) usage[key].standard += 1;
        if (isCreative) usage[key].creative += 1;
      });

      newTeams[tIndex].errors = errors;
    });

    Object.entries(usage).forEach(([pid, u]) => {
      const p = findPlayer(pid);
      const name = p?.label || `بازیکن ${pid}`;
      if (u.standard > 1) {
        hasError = true;
        newTeams.forEach((t) => {
          if (t.type !== "standard") return;
          const all = [...(t.main || []), ...(t.reserve || [])];
          if (all.includes(Number(pid))) {
            t.errors.player_multi_standard = `بازیکن «${name}» در بیش از یک تیم استاندارد انتخاب شده است.`;
          }
        });
      }
      if (u.creative > 1) {
        hasError = true;
        newTeams.forEach((t) => {
          if (t.type !== "creative") return;
          const all = [...(t.main || []), ...(t.reserve || [])];
          if (all.includes(Number(pid))) {
            t.errors.player_multi_creative = `بازیکن «${name}» در بیش از یک تیم ابداعی انتخاب شده است.`;
          }
        });
      }
    });

    setTeams(newTeams);
    return !hasError;
  };

  const canSubmit =
    registrationOpen &&
    !loading &&
    teams.some((t) => t.type && (t.main || []).filter(Boolean).length > 0 && summary.totalSlots > 0);

  /* ---------- payload builder (backend new shape) ---------- */

  const buildTeamPayload = (t) => {
    const members = [];

    (t.main || []).filter(Boolean).forEach((pid) => {
      const ins = (t.insurance || {})[String(pid)] || {};
      members.push({
        player_id: pid,
        role: "main",
        insurance_number: (ins.number || "").trim(),
        // ترجیح ISO برای بک‌اند (fallback به شمسی)
        insurance_issue_date: (ins.date_iso || ins.date || "").trim(),
      });
    });

    (t.reserve || []).filter(Boolean).forEach((pid) => {
      const ins = (t.insurance || {})[String(pid)] || {};
      members.push({
        player_id: pid,
        role: "sub",
        insurance_number: (ins.number || "").trim(),
        insurance_issue_date: (ins.date_iso || ins.date || "").trim(),
      });
    });

    return {
      name: t.name,
      style: t.type, // standard/creative
      members,
    };
  };

  const submitTeamsToBackend = async () => {
    const teamPayloads = teams.map(buildTeamPayload);

    // تک تیم
    if (teamPayloads.length === 1) {
      const r = await registerPoomsaeTeams(slug, teamPayloads[0]);

      const ids = [
        ...(Array.isArray(r?.enrollment_ids) ? r.enrollment_ids : []),
        ...(r?.enrollment_id != null ? [r.enrollment_id] : []),
      ]
        .map(Number)
        .filter(Number.isFinite);

      return { ...r, enrollment_ids: Array.from(new Set(ids)) };
    }

    // چند تیم: یکی‌یکی
    const results = [];
    const allIds = [];

    for (const one of teamPayloads) {
      // eslint-disable-next-line no-await-in-loop
      const r = await registerPoomsaeTeams(slug, one);
      results.push(r);

      const ids = [
        ...(Array.isArray(r?.enrollment_ids) ? r.enrollment_ids : []),
        ...(r?.enrollment_id != null ? [r.enrollment_id] : []),
      ]
        .map(Number)
        .filter(Number.isFinite);

      allIds.push(...ids);
    }

    const unique = Array.from(new Set(allIds));
    return { results, enrollment_ids: unique };
  };

  /* ---------- submit + payment ---------- */

  const handleSubmit = async () => {
    setErr("");

    if (!registrationOpen) {
      setErr("در حال حاضر ثبت‌نام این مسابقه غیرفعال است.");
      return;
    }
    if (!validateTeams()) {
      setErr("لطفاً خطاهای فرم تیم‌ها را برطرف کنید.");
      return;
    }
    if (!summary.totalSlots) {
      setErr("هیچ عضوی برای تیم‌ها انتخاب نشده است.");
      return;
    }
    if (!competition?.public_id) {
      setErr("شناسه مسابقه روی سرور یافت نشد.");
      return;
    }

    try {
      setSubmitting(true);

      const res = await submitTeamsToBackend();

      const eids = Array.isArray(res?.enrollment_ids) ? res.enrollment_ids : [];

      // اگر بک‌اند خودش payment_url داد
      if (res?.payment_url) {
        window.location.href = res.payment_url;
        return;
      }

      // اگر ثبت‌نام رایگان است: مستقیم برو صفحه کارت‌ها
      if (Number(summary.totalAmount || 0) === 0) {
        if (eids.length) {
          const qs = encodeURIComponent(eids.join(","));
          navigate(
            `/dashboard/${encodeURIComponent(role || "coach")}/enrollments/bulk?ids=${qs}`,
            { state: { ids: eids }, replace: true }
          );
          return;
        }
        setErr("ثبت انجام شد، اما enrollment_id از سرور برنگشت.");
        return;
      }

      // اگر مبلغ غیر صفر است: پرداخت انجام شود
      const intent = await createPaymentIntent({
        competitionPublicId: competition.public_id,
        amount: Number(summary.totalAmount || 0),
        description: `ثبت‌نام تیمی پومسه در مسابقه ${competition?.title || ""}`,
        style: "poomsae_team",
      });

      const intentPublicId = intent.public_id || intent.id;
      if (!intentPublicId) {
        setErr("ثبت تیم‌ها انجام شد، اما شناسهٔ پرداخت از سرور دریافت نشد.");
        return;
      }

      const params = new URLSearchParams();
      if (competition?.id) params.set("cid", String(competition.id));
      params.set("flow", "poomsae_team_after_payment");
      if (eids.length) params.set("ids", eids.join(","));

      const callbackUrl = `${window.location.origin}/#/payment/result?${params.toString()}`;

      const payRes = await startPaymentIntent(intentPublicId, { callbackUrl });

      if (payRes?.redirect_url) {
        window.location.href = payRes.redirect_url;
        return;
      }

      setErr("تیم‌ها ثبت شدند، اما لینک انتقال به درگاه بانکی از سرور دریافت نشد.");
    } catch (e) {
      setErr(e?.message || "خطا در ثبت تیم‌ها / شروع پرداخت");
    } finally {
      setSubmitting(false);
    }
  };

  /* ---------- UI ---------- */

  if (loading && !competition) {
    return (
      <div className="cd-container">
        <div className="cd-skeleton">در حال بارگذاری…</div>
      </div>
    );
  }

  if (!competition) {
    return (
      <div className="cd-container">
        <div className="cd-error">مسابقه یافت نشد.</div>
      </div>
    );
  }

  const titleText = competition.title || competition.name || "—";

  return (
    <div className="cd-container ptr-container" dir="rtl">
      {err && (
        <div className="cd-error" style={{ marginBottom: 12 }}>
          {err}
        </div>
      )}

      {/* header */}
      <div className="cd-hero small">
        <div className="cd-hero-body">
          <h1 className="cd-title">ثبت‌نام تیمی پومسه – {titleText}</h1>
          <div className="cd-chips">
            <span className="cd-chip">
              هزینه ورودی هر نفر:{" "}
              <strong>{toFa(Number(entryFee || 0).toLocaleString())}</strong> تومان
            </span>
            <span className={`cd-chip ${registrationOpen ? "ok" : "nok"}`}>
              ثبت‌نام تیمی: <strong>{registrationOpen ? "باز" : "بسته"}</strong>
            </span>
          </div>
        </div>
      </div>

      {!registrationOpen && (
        <div className="cd-note cd-note--poomsae" style={{ marginBottom: 16 }}>
          ثبت‌نام تیمی فقط در بازه‌ی تاریخ شروع و پایان ثبت‌نام مسابقه فعال است.
        </div>
      )}

      {/* teams */}
      <section className="cd-section">
        <h2 className="cd-section-title">تیم‌ها</h2>

        {teams.map((t, idx) => {
          const slots = SLOTS_BY_TYPE[t.type] || { main: 0, reserve: 0 };
          const selectedIdsInThisTeam = new Set(
            [...(t.main || []), ...(t.reserve || [])].filter(Boolean)
          );

          const renderMemberCard = (label, pid, onSelect, currentValue, errorKey) => {
            const ins = pid ? (t.insurance?.[String(pid)] || {}) : {};
            const errNo = pid ? t.errors?.[`ins_no_${pid}`] : null;
            const errDate = pid ? t.errors?.[`ins_date_${pid}`] : null;

            const optionEls = playerOptions.map((p) => (
              <option
                key={p.id}
                value={p.id}
                disabled={selectedIdsInThisTeam.has(p.id) && String(p.id) !== String(currentValue)}
              >
                {p.label}
              </option>
            ));

            return (
              <div className="poomsae-member-card">
                <label className="cd-label">{label}</label>

                <select
                  className="cd-input"
                  value={currentValue || ""}
                  onChange={onSelect}
                  disabled={!registrationOpen}
                >
                  <option value="">انتخاب بازیکن…</option>
                  {optionEls}
                </select>

                {errorKey && t.errors?.[errorKey] && (
                  <div className="cd-error" style={{ marginTop: 6 }}>
                    {t.errors[errorKey]}
                  </div>
                )}

                {pid && (
                  <>
                    <div className="insurance-grid" style={{ marginTop: 10 }}>
                      <div>
                        <label className="cd-label">شماره بیمه</label>
                        <input
                          className="cd-input"
                          value={ins.number || ""}
                          onChange={(e) =>
                            handleInsuranceChange(t.tmpId, pid, "number", e.target.value)
                          }
                          placeholder="مثلاً ۱۲۳۴۵۶"
                          disabled={!registrationOpen}
                        />
                        {errNo && (
                          <div className="cd-error" style={{ marginTop: 6 }}>
                            {errNo}
                          </div>
                        )}
                      </div>

                      <div>
                        <label className="cd-label">تاریخ صدور بیمه (شمسی)</label>
                        {renderInsuranceDatePicker(t.tmpId, pid, ins.date)}
                        {errDate && (
                          <div className="cd-error" style={{ marginTop: 6 }}>
                            {errDate}
                          </div>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            );
          };

          return (
            <div key={t.tmpId} className="cd-card" style={{ marginBottom: 16 }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 2fr auto",
                  gap: 12,
                  alignItems: "flex-end",
                  marginBottom: 8,
                }}
              >
                <div>
                  <label className="cd-label">نام تیم</label>
                  <input
                    className="cd-input"
                    value={t.name}
                    onChange={(e) =>
                      updateTeam(t.tmpId, {
                        name: e.target.value,
                        errors: { ...t.errors, name: undefined },
                      })
                    }
                    placeholder={`مثلاً تیم ${idx + 1}`}
                    disabled={!registrationOpen}
                  />
                  {t.errors.name && (
                    <div className="cd-error" style={{ marginTop: 4 }}>
                      {t.errors.name}
                    </div>
                  )}
                </div>

                <div>
                  <label className="cd-label">نوع تیم</label>
                  <select
                    className="cd-input"
                    value={t.type || ""}
                    onChange={(e) => handleTypeChange(t.tmpId, e.target.value)}
                    disabled={!registrationOpen}
                  >
                    <option value="">انتخاب کنید…</option>
                    <option value="standard">پومسه استاندارد (۳ اصلی + ۲ ذخیره)</option>
                    <option value="creative">پومسه ابداعی (۲ اصلی + ۱ ذخیره)</option>
                  </select>
                  {t.errors.type && (
                    <div className="cd-error" style={{ marginTop: 4 }}>
                      {t.errors.type}
                    </div>
                  )}
                </div>

                <div style={{ textAlign: "left" }}>
                  <button
                    type="button"
                    className="btn btn-light"
                    onClick={() => removeTeam(t.tmpId)}
                    disabled={teams.length <= 1 || !registrationOpen}
                    title={
                      teams.length <= 1
                        ? "حداقل یک تیم باید وجود داشته باشد"
                        : "حذف این تیم"
                    }
                  >
                    حذف تیم
                  </button>
                </div>
              </div>

              {t.type && (
                <div className="cd-grid">
                  {/* main */}
                  <div className="poomsae-members-grid">
                    {Array.from({ length: slots.main }).map((_, i) => (
                      <div key={`main-${i}`}>
                        {renderMemberCard(
                          `عضو اصلی ${toFa(i + 1)}`,
                          t.main?.[i],
                          (e) => handleMemberChange(t.tmpId, "main", i, e.target.value || null),
                          t.main?.[i],
                          `main_${i}`
                        )}
                      </div>
                    ))}
                  </div>

                  {/* reserve */}
                  <div className="poomsae-members-grid">
                    {Array.from({ length: slots.reserve }).map((_, i) => (
                      <div key={`reserve-${i}`}>
                        {renderMemberCard(
                          `بازیکن ذخیره ${toFa(i + 1)} (اختیاری)`,
                          t.reserve?.[i],
                          (e) =>
                            handleMemberChange(t.tmpId, "reserve", i, e.target.value || null),
                          t.reserve?.[i],
                          null
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {t.errors.age_mismatch && (
                <div className="cd-error" style={{ marginTop: 10 }}>
                  {t.errors.age_mismatch}
                </div>
              )}
              {t.errors.belt_mismatch && (
                <div className="cd-error" style={{ marginTop: 10 }}>
                  {t.errors.belt_mismatch}
                </div>
              )}
              {t.errors.player_multi_standard && (
                <div className="cd-error" style={{ marginTop: 10 }}>
                  {t.errors.player_multi_standard}
                </div>
              )}
              {t.errors.player_multi_creative && (
                <div className="cd-error" style={{ marginTop: 10 }}>
                  {t.errors.player_multi_creative}
                </div>
              )}
            </div>
          );
        })}

        <button
          type="button"
          className="btn btn-outline"
          onClick={addTeam}
          disabled={!registrationOpen}
          title={!registrationOpen ? "افزودن تیم جدید فقط در بازه‌ی ثبت‌نام مجاز است" : ""}
        >
          + افزودن تیم جدید
        </button>
      </section>

      {/* summary */}
      <section className="cd-section">
        <h2 className="cd-section-title">خلاصه</h2>

        <div className="cd-discount-summary">
          <div>
            تعداد تیم‌های استاندارد: <strong>{toFa(summary.standardTeams)}</strong>
          </div>
          <div>
            تعداد تیم‌های ابداعی: <strong>{toFa(summary.creativeTeams)}</strong>
          </div>
          <div>
            تعداد کل اسلات‌های پرشده (نفر): <strong>{toFa(summary.totalSlots)}</strong>
          </div>
          <div>
            مبلغ کل قابل پرداخت:{" "}
            <strong>{toFa(Number(summary.totalAmount || 0).toLocaleString())}</strong> تومان
          </div>
        </div>

        <div className="cd-actions" style={{ marginTop: 16 }}>
          <button
            className="btn btn-light"
            onClick={() =>
              navigate(
                `/dashboard/${encodeURIComponent(role || "coach")}/competitions/${encodeURIComponent(slug)}`
              )
            }
          >
            بازگشت
          </button>

          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={!canSubmit || submitting}
            title={
              !registrationOpen
                ? "ثبت‌نام تیمی در حال حاضر بسته است"
                : !summary.totalSlots
                ? "هیچ عضوی برای تیم‌ها انتخاب نشده است"
                : ""
            }
          >
            {submitting
              ? "در حال ثبت…"
              : Number(summary.totalAmount || 0) === 0
              ? "ثبت نهایی"
              : "تأیید و پرداخت"}
          </button>
        </div>
      </section>
    </div>
  );
}
