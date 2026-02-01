// src/components/Login/panel/Dashboard.jsx
import React, { useEffect, useRef, useState, useMemo } from "react";
import { useNavigate, Outlet, useParams, useLocation, matchPath } from "react-router-dom";
import Sidebar from "./Sidebar";
import StatsCard from "./StatsCard";
import MainContent from "./MainContent";
import PersonalInfoForm from "../panel/maincontentpanel/PersonalInfoForm";
import CircularsSection from "./CircularsSection";
import NewsSection from "./NewsSection";
import StudentsTable from "./maincontentpanel/StudentsTable";
import ChangeCoachClubs from "./maincontentpanel/ChangeCoachClubs";
import ClubCoachesManagement from "./maincontentpanel/ClubCoachesManagement";
import CoachRequests from "./maincontentpanel/CoachRequests";
import HeyatCoachesTable from "./maincontentpanel/HeyatCoachesTable";
import HeyatRefereesTable from "./maincontentpanel/HeyatRefereesTable";
import HeyatClubsTable from "./maincontentpanel/HeyatClubsTable";
import HeyatCreateNews from "./maincontentpanel/HeyatCreateNews";
import MatchesSection from "./MatchesSection";
import SeminarsSection from "../seminar/SeminarsSection";

import "./dashboard.css";

// کمکی محلی برای تشخیص نقش‌های شبیه هیئت/باشگاه
const isClubLike = (r) => ["club", "heyat", "board"].includes(String(r || "").toLowerCase());

const Dashboard = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { role: roleFromRoute } = useParams();

  const logoutTimerRef = useRef(null);

  // نقش ذخیره‌شده (منبع حقیقت برای مسیرها)
  const storedRole = useMemo(
    () => (localStorage.getItem("user_role") || "guest").toLowerCase(),
    []
  );

  const [role, setRole] = useState(null);
  const [selectedSection, setSelectedSection] = useState("matches");
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 768);
  const [showSidebar, setShowSidebar] = useState(() => !(window.innerWidth <= 768));

  // آیا در یکی از صفحات تودرتو (جزئیات/جدول/ثبت‌نام/نتایج/کارت) هستیم؟
  const inNestedView = useMemo(() => {
    const p = location.pathname;
    return Boolean(
      matchPath("/dashboard/:role/competitions/:slug", p) ||
      matchPath("/dashboard/:role/competitions/:slug/*", p) ||
      matchPath("/dashboard/:role/competitions/:slug/register/*", p) ||
      matchPath("/dashboard/:role/competitions/:slug/bracket", p) ||
      matchPath("/dashboard/:role/competitions/:slug/results", p) ||
      matchPath("/dashboard/:role/enrollments/:enrollmentId", p) ||
      matchPath("/dashboard/:role/enrollments/:enrollmentId/*", p) ||
      matchPath("/dashboard/:role/courses/:slug", p) ||
      matchPath("/dashboard/:role/courses/:slug/*", p) ||
      matchPath("/dashboard/:role/courses/:slug/register/*", p)
    );
  }, [location.pathname]);

  const logout = () => {
    const savedRole = localStorage.getItem("user_role");
    // پاک‌سازی توکن‌ها
    [
      "both_token",
      "player_token",
      "coach_token",
      "referee_token",
      "club_token",
      "heyat_token",
      "board_token",
      "access_token",
    ].forEach((k) => localStorage.removeItem(k));
    if (savedRole) {
      localStorage.removeItem(`${savedRole}_token`);
      localStorage.removeItem("user_role");
    }
    navigate("/", { replace: true });
  };

  const resetLogoutTimer = () => {
    if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current);
    logoutTimerRef.current = setTimeout(logout, 10 * 60 * 1000); // 10 دقیقه
  };

  // احراز هویت + همگام‌سازی نقش + ریسایز + تایمر inactivity
  useEffect(() => {
    const savedRole = localStorage.getItem("user_role");
    const token = savedRole && localStorage.getItem(`${savedRole}_token`);
    if (!savedRole || !token) {
      navigate("/", { replace: true });
      return;
    }
    setRole(savedRole);

    // اگر نقش URL با نقش ذخیره‌شده نخواند، URL را تصحیح کن ولی suffix مسیر را نگه دار
   if (roleFromRoute && roleFromRoute !== savedRole) {
     // هرچه بعد از /dashboard/:role آمده را نگه می‌داریم (مثلاً /competitions/xyz/bracket)
     const suffix = location.pathname.replace(/^\/dashboard\/[^/]+/, "");
     navigate(`/dashboard/${encodeURIComponent(savedRole)}${suffix}${location.search}`, { replace: true });
     return;
   }

    const handleResize = () => {
      const nowMobile = window.innerWidth <= 768;
      setIsMobile(nowMobile);
      setShowSidebar(!nowMobile);
    };

    window.addEventListener("resize", handleResize);
    const events = ["mousemove", "keydown", "click", "scroll", "touchstart", "touchmove"];
    events.forEach((e) => window.addEventListener(e, resetLogoutTimer));
    resetLogoutTimer();

    return () => {
      window.removeEventListener("resize", handleResize);
      events.forEach((e) => window.removeEventListener(e, resetLogoutTimer));
      clearTimeout(logoutTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, roleFromRoute]);

  // سینک بخش انتخابی با querystring (?section=...)
//  اگر در route تو در تو هستیم، اجازه بده Outlet رندر بشه و بخش‌ها تغییر نکنن
  useEffect(() => {
    if (inNestedView) return;
    const qs = new URLSearchParams(location.search);
    const sec = qs.get("section") || "matches";
    setSelectedSection(sec);
  }, [location.search, inNestedView]);

  if (!role) return null;

  const renderContent = () => {
    switch (selectedSection) {
      case "profile":
        return <PersonalInfoForm role={role} />;
      case "circulars":
        return <CircularsSection role={role} />;
      case "news":
        return <NewsSection role={role} />;
      case "matches":
        return <MatchesSection role={role} />;
      case "students":
        return <StudentsTable role={role} />;
      case "club-change":
        return <ChangeCoachClubs role={role} />;
      case "club-students":
        return <StudentsTable role={role} view="club" />;
      case "club-coaches":
        return <ClubCoachesManagement role={role} />;
      case "club-requests":
        return <CoachRequests role={role} />;
      case "heyat-coaches":
        return <HeyatCoachesTable role={role} />;
      case "heyat-referees":
        return <HeyatRefereesTable role={role} />;
      case "heyat-clubs":
        return <HeyatClubsTable role={role} />;
      case "heyat-create-news":
        return <HeyatCreateNews role={role} />;
      case "courses":
        return <SeminarsSection role={role} />;
      default:
        return <MainContent role={role} selectedSection={selectedSection} />;
    }
  };

  const handleSectionSelect = (key) => {
    setSelectedSection(key);
    // مسیر را با نقش ذخیره‌شده بساز تا همیشه با منطق ریدایرکت یکی باشد
    const r = (localStorage.getItem("user_role") || role || storedRole);
    navigate(`/dashboard/${encodeURIComponent(r)}?section=${encodeURIComponent(key)}`);
  };

  return (
    <div className="dashboard-container">
      {isMobile && (
        <button
          className="toggle-sidebar-btn"
          onClick={() => setShowSidebar((prev) => !prev)}
          aria-label={showSidebar ? "بستن منو" : "نمایش منو"}
        >
          {showSidebar ? "بستن منو" : "نمایش منو"}
        </button>
      )}

      <Sidebar
        className={isMobile ? (showSidebar ? "show" : "") : ""}
        onLogout={logout}
        onSectionSelect={handleSectionSelect}
        selectedSection={selectedSection}
        role={role}
        isClubLike={isClubLike(role)}
      />

      <div className="dashboard-main">
        {/* آمار فقط در صفحات اصلی داشبورد (دسکتاپ) */}
        {!isMobile && !inNestedView && <StatsCard role={role} />}

        {/* در صفحات تو‌در‌تو (جزئیات/جدول/ثبت‌نام/نتایج/کارت) Outlet رندر می‌شود */}
        {inNestedView ? (
          <Outlet context={{ role, isClubLike: isClubLike(role) }} key={location.pathname} />
        ) : (
          renderContent()
        )}
      </div>
    </div>
  );
};

export default Dashboard;
