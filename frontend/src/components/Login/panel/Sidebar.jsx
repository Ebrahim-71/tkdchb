// src/components/dashboard/Sidebar.jsx
import React, { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import placeholderImage from "../../../assets/img/avatar-placeholder.png";
import "./dashboard.css";

const API_BASE = "https://api.chbtkd.ir";

const getRoleInPersian = (role) => {
  switch (role) {
    case "player": return "بازیکن";
    case "coach": return "مربی";
    case "referee": return "داور";
    case "both": return "مربی و داور";
    case "club": return "باشگاه";
    case "heyat": return "هیئت";
    default: return "کاربر";
  }
};

const menuItemsByRole = {
  player: [
    { key: "profile", label: "اطلاعات کاربر" },
    { key: "matches", label: "مسابقات" },
    { key: "exams", label: "آزمون‌ها" },
    { key: "courses", label: "دوره‌های آموزشی" },
    { key: "circulars", label: "بخشنامه‌ها" },
    { key: "news", label: "اخبار استان و شهرستان" },
  ],
  coach: [
    { key: "profile", label: "اطلاعات کاربر" },
    { key: "matches", label: "مسابقات" },
    { key: "exams", label: "آزمون‌ها" },
    { key: "courses", label: "دوره‌های آموزشی" },
    { key: "students", label: "شاگردان" },
    { key: "club-change", label: "تغییر باشگاه" },
    { key: "club-requests", label: "درخواست‌های باشگاه" },
    { key: "circulars", label: "بخشنامه‌ها" },
    { key: "news", label: "اخبار استان و شهرستان" },
  ],
  referee: [
    { key: "profile", label: "اطلاعات کاربر" },
    { key: "matches", label: "مسابقات" },
    { key: "exams", label: "آزمون‌ها" },
    { key: "courses", label: "دوره‌های آموزشی" },
    { key: "circulars", label: "بخشنامه‌ها" },
    { key: "news", label: "اخبار استان و شهرستان" },
  ],
  both: [
    { key: "profile", label: "اطلاعات کاربر" },
    { key: "matches", label: "مسابقات" },
    { key: "exams", label: "آزمون‌ها" },
    { key: "courses", label: "دوره‌های آموزشی" },
    { key: "students", label: "شاگردان" },
    { key: "club-change", label: "تغییر باشگاه" },
    { key: "club-requests", label: "درخواست‌های باشگاه" },
    { key: "circulars", label: "بخشنامه‌ها" },
    { key: "news", label: "اخبار استان و شهرستان" },
  ],
  club: [
    { key: "matches", label: "مسابقات" },
    { key: "exams", label: "آزمون‌ها" },
    { key: "courses", label: "دوره‌های آموزشی" },
    { key: "club-coaches", label: "مربیان باشگاه" },
    { key: "club-students", label: "شاگردان باشگاه" },
    { key: "circulars", label: "بخشنامه‌ها" },
    { key: "news", label: "اخبار استان و شهرستان" },
  ],
  heyat: [
    { key: "matches", label: "مسابقات" },
    { key: "exams", label: "آزمون‌ها" },
    { key: "courses", label: "دوره‌های آموزشی" },
    { key: "students", label: "شاگردان" },
    { key: "heyat-coaches", label: "مربی‌ها" },
    { key: "heyat-referees", label: "داوران" },
    { key: "heyat-clubs", label: "باشگاه‌ها" },
    { key: "circulars", label: "بخشنامه‌ها" },
    { key: "news", label: "اخبار استان و شهرستان" },
    { key: "heyat-create-news", label: "ایجاد اخبار هیئت شهرستان" },
  ],
};

const Sidebar = ({ onLogout, onSectionSelect, selectedSection, className = "" }) => {
  const [profile, setProfile] = useState(null);
  const [hasNewClubRequests, setHasNewClubRequests] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const savedRole = localStorage.getItem("user_role");
    const token = savedRole && localStorage.getItem(`${savedRole}_token`);
    if (!savedRole || !token) {
      navigate("/");
      return;
    }

    axios
      .get(`${API_BASE}/api/auth/dashboard/${savedRole}/`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => {
        setProfile(res.data);

        if (["coach", "both"].includes(res.data.role)) {
          axios
            .get(`${API_BASE}/api/auth/coach/requests/`, {
              headers: { Authorization: `Bearer ${token}` },
            })
            .then((res2) => {
              const hasPending = res2.data.some((r) => r.status === "pending");
              setHasNewClubRequests(hasPending);
            })
            .catch((err) => {
              console.error("خطا در دریافت درخواست‌های باشگاه", err);
            });
        }
      })
      .catch((err) => {
        console.error("خطا در دریافت پروفایل", err);
        if (err.response?.status === 401) {
          localStorage.clear();
          navigate("/");
        }
      });
  }, [navigate]);

  const handleLogout = () => {
    const savedRole = localStorage.getItem("user_role");
    if (savedRole) {
      localStorage.removeItem(`${savedRole}_token`);
      localStorage.removeItem("user_role");
    }
    onLogout?.();
  };

  const role = profile?.role || localStorage.getItem("user_role") || "player";
  const menuItems =
    role === "both"
      ? Array.from(
          new Map(
            [...menuItemsByRole["coach"], ...menuItemsByRole["referee"]].map((i) => [i.key, i])
          ).values()
        )
      : menuItemsByRole[role] || [];

  const handleSectionClick = (key) => {
    navigate(
      `/dashboard/${encodeURIComponent(role)}?section=${encodeURIComponent(key)}`,
      { replace: false }
    );
    onSectionSelect && onSectionSelect(key);
  };

  return (
    <div className={`sidebar ${className}`}>
      <div className="sidebar-header">
        <div className="profile-image-wrapper">
          <img
            src={profile?.profile_image_url || placeholderImage}
            alt="پروفایل"
            className="profile-image"
            onError={(e) => (e.currentTarget.src = placeholderImage)}
          />
        </div>
        <div className="profile-info">
          <h3 className="profile-name">
            {role === "club" && profile?.club_name
              ? profile.club_name
              : role === "heyat" && profile?.board_name
              ? profile.board_name
              : profile?.full_name || "..."}
          </h3>

          <div className="profile-role-logout">
            <span className="role-label">{getRoleInPersian(role)}</span>
            <button className="logout-btn" onClick={handleLogout}>خروج</button>
          </div>
        </div>
      </div>

      <hr className="sidebar-divider" />

      <ul className="sidebar-menu">
        {menuItems.map((item) => (
          <li
            key={item.key}
            className={item.key === selectedSection ? "active" : ""}
            onClick={() => handleSectionClick(item.key)}
          >
            {item.label}
            {item.key === "club-requests" && hasNewClubRequests && (
              <span className="badge-dot" />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default Sidebar;
