import React, { useEffect, useState } from 'react';
import './header.css';
import logo from '../../../assets/img/logo.png';

const API_BASE = "https://api.chbtkd.ir";

const Header = () => {
  const [backgroundImage, setBackgroundImage] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/api/header-background/`)
      .then(res => res.json())
      .then(data => {
        if (data.background_image) {
          const fullURL = `${API_BASE}${data.background_image}`;
          setBackgroundImage(fullURL);
        }
      })
      .catch(err => console.error("خطا در دریافت API:", err));
  }, []);

  return (
    <header className="header" style={{ backgroundImage: `url(${backgroundImage})` }}>
      <div className="header-overlay"></div>

      <div className="logo-container">
        <div className="header-text">
          <h1 className="site-title-main">هیئت تکواندو</h1>
          <h2 className="site-title-sub">استان چهارمحال و بختیاری</h2>
        </div>
        <img src={logo} alt="Logo" className="logo" />
      </div>
    </header>
  );
};

export default Header;
