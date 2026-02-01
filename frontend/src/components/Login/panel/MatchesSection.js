// src/components/Login/panel/MatchesSection.jsx
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import PaginatedList from "../../common/PaginatedList";
import MatchCard from "./maincontentpanel/MatchCard";
import CoachAgreementFlow from "../competitions/CoachAgreementFlow";
import { getCompetitionsForRole } from "../../../api/competitions";

/* ---------- Helpers ---------- */
function getUserRoles() {
  const raw = String(localStorage.getItem("user_role") || "").toLowerCase();
  const parts = raw.split(/[,\s]+/).filter(Boolean);
  const s = new Set(parts);
  if (s.has("both")) {
    s.add("player");
    s.add("coach");
    s.delete("both");
  }
  return Array.from(s);
}

function roleForPath(roles) {
  if (roles.includes("coach")) return "coach";
  if (roles.includes("referee")) return "referee";
  if (roles.includes("club")) return "club";
  if (roles.includes("heyat")) return "heyat";
  if (roles.includes("board")) return "board";
  if (roles.includes("player")) return "player";
  return "guest";
}

const isClubLike = (roles) =>
  roles.some((r) => ["club", "heyat", "board"].includes(String(r).toLowerCase()));

function isKyorugi(comp) {
  const s = String(comp?.style_display || comp?.style || "").toLowerCase();
  return s.includes("kyorugi") || s.includes("کیوروگی");
}

function isPoomsae(comp) {
  const s = String(comp?.style_display || comp?.style || "").toLowerCase();
  return s.includes("poomsae") || s.includes("پومسه");
}

/* ---------- Component ---------- */
const MatchesSection = () => {
  const navigate = useNavigate();

  const roles = useMemo(() => getUserRoles(), []);
  const rolePath = useMemo(() => roleForPath(roles), [roles]);
  const storedRole = useMemo(() => {
    // نقش واقعی ذخیره‌شده؛ همانی که Dashboard انتظار دارد (ممکن است 'both' باشد)
    const raw = String(localStorage.getItem("user_role") || "").toLowerCase();
    const allowed = ["coach","player","referee","club","heyat","board","both"];
    return allowed.includes(raw) ? raw : "player";
  }, []);

  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const [showTermsModal, setShowTermsModal] = useState(false);
  const [selectedMatch, setSelectedMatch] = useState(null);

  const isMobile = typeof window !== "undefined" ? window.innerWidth <= 768 : false;

  const pushToDetails = (slug, opts = {}) => {
    if (!slug) return;
    const base = `/dashboard/${encodeURIComponent(storedRole)}/competitions/${encodeURIComponent(slug)}`;
    navigate(opts.view === "details" ? `${base}?view=details` : base);
  };

  const handleDetailsClick = (comp) => {
    if (!comp?.public_id) return;

    const coachLike = roles.includes("coach") || roles.includes("both");
    const refLike = roles.includes("referee") || isClubLike(roles);

    // مربی: برای کیوروگی و پومسه مودال تعهدنامه باز شود
    if (coachLike && (isKyorugi(comp) || isPoomsae(comp))) {
      setSelectedMatch(comp);
      setShowTermsModal(true);
      return;
    }

    // داور/باشگاه/هیئت → مستقیم
    if (refLike) {
      pushToDetails(comp.public_id, { view: "details" });
      return;
    }

    // بازیکن/سایر → مستقیم
    pushToDetails(comp.public_id);
  };

  const handleModalCancel = () => {
    setShowTermsModal(false);
    setSelectedMatch(null);
  };

  const handleModalDone = (slugFromChild) => {
    const slug = slugFromChild || selectedMatch?.public_id;
    setShowTermsModal(false);
    setSelectedMatch(null);
    if (slug) pushToDetails(slug);
  };

  /* ---------- دریافت مسابقات ---------- */
  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setErr("");

      try {
        let data = await getCompetitionsForRole(rolePath);
        if (!alive) return;

        data = Array.isArray(data) ? data : [];

        const getTime = (x) => {
          const s =
            x?.created_at ||
            x?.competition_date ||
            x?.start_date ||
            x?.event_date ||
            null;
          const t = s ? Date.parse(s) : NaN;
          return Number.isNaN(t) ? -Infinity : t;
        };

        // جدیدترها جلو + tie-breaker پایدار
        data.sort((a, b) => {
          const tb = getTime(b);
          const ta = getTime(a);
          if (tb !== ta) return tb - ta;
          return (b?.id ?? 0) - (a?.id ?? 0);
        });

        setMatches(data);
        if (!data.length && isClubLike(roles)) {
          setErr("مسابقه‌ای برای نمایش پیدا نشد.");
        }
      } catch (e) {
        if (!alive) return;
        const msg =
          e?.status === 401 ? "ابتدا وارد حساب شوید." : e?.message || "خطا در دریافت مسابقات";
        setErr(msg);
        setMatches([]);
      } finally {
        alive && setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [roles, rolePath]);

  /* ---------- UI ---------- */
  return (
    <div style={{ padding: "2rem" }} dir="rtl">
      <h2>مسابقات</h2>

      {loading ? (
        <div>در حال بارگذاری…</div>
      ) : err ? (
        <div style={{ color: "#b91c1c", marginBottom: 12 }}>{err}</div>
      ) : matches.length === 0 ? (
        <div>مسابقه‌ای یافت نشد.</div>
      ) : (
        <PaginatedList
          items={matches}
          itemsPerPage={4}
          renderItem={(item, index) => (
            <div
              key={item.public_id || item.id || index}
              style={{
                width: isMobile ? "90%" : "100%",
                margin: "10px 20px",
                display: "inline-flex",
                flexDirection: "column",
              }}
            >
              <MatchCard match={item} onDetailsClick={() => handleDetailsClick(item)} />
            </div>
          )}
        />
      )}

      {/* مودال تعهدنامه */}
      {showTermsModal && selectedMatch && (
        <CoachAgreementFlow
          competition={selectedMatch}
          onDone={handleModalDone}
          onCancel={handleModalCancel}
        />
      )}
    </div>
  );
};

export default MatchesSection;
