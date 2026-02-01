// src/components/pages/home/sections/userpanel/UserPanel.jsx
import React, { useState } from "react";
import "./userpanel.css";

import playerImg from "../../../../assets/img/player.png";
import coachImg from "../../../../assets/img/coach.png";
import clubImg from "../../../../assets/img/club.png";
import heyatImg from "../../../../assets/img/heyat.png";

import PlayerRegisterModal from "../../../Register/RegisterModal.jsx";
import LoginModal from "../../../Login/LoginModal.jsx";
import ForgotPasswordModal from "../../../Login/ForgotPasswordModal.jsx";

const panelItems = [
  { title: "بازیکن",      image: playerImg },
  { title: "مربی | داور", image: coachImg },
  { title: "باشگاه",      image: clubImg },
  { title: "هیأت",        image: heyatImg },
];

const UserPanel = () => {
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [selectedRegisterRole, setSelectedRegisterRole] = useState(""); // player | coach | club

  const [showLoginModal, setShowLoginModal] = useState(false);
  const [selectedLoginRoleGroup, setSelectedLoginRoleGroup] = useState("player"); // player | coachref | club | heyat

  const [showForgotModal, setShowForgotModal] = useState(false);

  // دکمه‌ی ورود هر کارت
  const handleLoginClick = (title) => {
    if (title === "هیأت")             setSelectedLoginRoleGroup("heyat");
    else if (title === "بازیکن")      setSelectedLoginRoleGroup("player");
    else if (title === "مربی | داور") setSelectedLoginRoleGroup("coachref");
    else if (title === "باشگاه")       setSelectedLoginRoleGroup("club");
    setShowLoginModal(true);
  };

  // دکمه‌ی ثبت‌نام هر کارت (هیأت ثبت‌نام ندارد)
  const handleRegisterClick = (title) => {
    if (title === "بازیکن")           setSelectedRegisterRole("player");
    else if (title === "مربی | داور") setSelectedRegisterRole("coach");
    else if (title === "باشگاه")       setSelectedRegisterRole("club");
    setShowRegisterModal(true);
  };

  return (
    <div className="user-panel-wrapper">
      <div className="user-panel">
        <div className="panel">
          <h2>ورود | ثبت نام</h2>

          <div className="panel-wrpper">
            {panelItems.map((item, i) => (
              <div key={i} className="panel-box">
                <img src={item.image} alt={item.title} className="panel-img" />
                <div className="overlay">
                  <h3>{item.title}</h3>

                  <div className="panel-buttons">
                    <button onClick={() => handleLoginClick(item.title)}>ورود</button>
                    {item.title !== "هیأت" && (
                      <button onClick={() => handleRegisterClick(item.title)}>ثبت‌نام</button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

        </div>
      </div>

      {showRegisterModal && (
        <PlayerRegisterModal
          role={selectedRegisterRole}              // "player" | "coach" | "club"
          onClose={() => setShowRegisterModal(false)}
        />
      )}

      {showLoginModal && (
        <LoginModal
          role={selectedLoginRoleGroup}
          onClose={() => setShowLoginModal(false)}
          onForgotPassword={() => {
            setShowLoginModal(false);
            setShowForgotModal(true);
          }}
        />

      )}

      {showForgotModal && (
        <ForgotPasswordModal onClose={() => setShowForgotModal(false)} />
      )}
    </div>
  );
};

export default UserPanel;
