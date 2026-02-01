// components/common/PrivateRoute.jsx
import React from "react";
import { Navigate, useLocation } from "react-router-dom";

function pickToken() {
  const role = localStorage.getItem("user_role") || "";
  const keys = [
    `${role}_token`,
    "both_token",
    "player_token",
    "coach_token",
    "referee_token",
    "club_token",
    "heyat_token",
    "access_token",
  ];
  for (const k of keys) {
    const v = localStorage.getItem(k);
    if (v && v !== "null" && v !== "undefined") return v;
  }
  return null;
}

const PrivateRoute = ({ children }) => {
  const location = useLocation();
  const token = pickToken();

  if (!token) {
    return <Navigate to="/" replace state={{ from: location }} />;
  }
  return children;
};

export default PrivateRoute;
