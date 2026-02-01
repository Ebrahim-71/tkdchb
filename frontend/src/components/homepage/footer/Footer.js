import React from 'react';
import {  FaPhoneAlt,FaMapMarkerAlt } from 'react-icons/fa';
import instagramIcon from '../../../assets/icons/instagram.png';
import eitaaIcon from '../../../assets/icons/eitaa-icon-colorful.png';
import './Footer.css';

const Footer = () => {
  return (
    <footer className="footer">
      <div className="footer-container">

        {/* اطلاعات تماس */}
        <div className="footer-section">
          <h4>ارتباط با ما</h4>
          <p><FaMapMarkerAlt />  شهرکرد، میدان امام حسین ،اداره ورزش و جوانان ،هیئت تکواندو استان</p>
          <p><FaPhoneAlt /> ۰۳۸۳۲۲۲۶۶۸۶</p>
        </div>

        {/* شبکه‌های اجتماعی */}
        <div className="footer-section">
          <h4>ما را در شبکه‌های اجتماعی دنبال کنید</h4>
          <div className="social-icons">
            <a href="https://www.instagram.com/taekwondo.sh.k?igsh=MXhiMjlzaWFycHFwYw==" target="_blank" rel="noopener noreferrer">
              <img src={instagramIcon} alt="Instagram" />
            </a>
            <a href="https://eitaa.com/tkdchb" target="_blank" rel="noopener noreferrer">
              <img src={eitaaIcon} alt="Eitaa" />
            </a>
          </div>
        </div>
      </div>

      {/* کپی‌رایت */}
      <div className="footer-bottom">
        © {new Date().getFullYear()} هیئت تکواندو چهارمحال و بختیاری - تمامی حقوق محفوظ است.
      </div>
    </footer>
  );
};

export default Footer;
