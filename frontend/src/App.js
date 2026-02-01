// src/App.js
import React, { useState, useEffect } from "react";
import {
  HashRouter as Router,
  Routes,
  Route,
  useLocation,
} from "react-router-dom";

import { Helmet } from "react-helmet";

import Header from "./components/homepage/heder/header";
import NewsSlider from "./components/homepage/main/slider/newsslider";
import ImageSlider from "./components/homepage/main/slider/Slider";
import CircularSlider from "./components/homepage/main/slider/CircularSlider";
import Footer from "./components/homepage/footer/Footer";
import NewsDetail from "./pages/NewsDetail";
import CircularDetail from "./pages/CircularDetail";
import RegisterCoachPage from "./pages/RegisterCoachPage";
import RegisterplayerPage from "./pages/RegisterplayerPage";
import RegisterClubPage from "./pages/RegisterClubPage";
import Userpanel from "./components/homepage/main/userpanel/userpanel";

import Dashboard from "./components/Login/panel/Dashboard";
import PrivateRoute from "./components/common/PrivateRoute";
import EnrollmentCard from "./components/Login/competitions/EnrollmentCard";
import CoachRegisterStudents from "./components/Login/competitions/CoachRegisterStudents";
import EnrollmentCardsBulk from "./components/Login/competitions/EnrollmentCardsBulk";
import CompetitionDetails from "./components/Login/competitions/CompetitionDetails";
import CompetitionBracket from "./components/Login/competitions/CompetitionBracket";
import CompetitionResults from "./components/Login/competitions/CompetitionResults";
import SeminarDetail from "./components/Login/seminar/SeminarDetail";
import PoomsaeTeamRegister from "./components/Login/competitions/PoomsaeTeamRegister";

// ✅ صفحه نتیجه پرداخت
import PaymentResult from "./pages/PaymentResult";

import "./App.css";

/* Scroll to top on route change */
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

const MainPage = () => {
  const location = useLocation();
  const [showSlider, setShowSlider] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 768);

  // مسیرهایی که اسلایدر/پنل کاربری نمایش داده نشه
  const isSpecialPage =
    location.pathname.startsWith("/news") ||
    location.pathname.startsWith("/circular") ||
    location.pathname.startsWith("/register") ||
    location.pathname.startsWith("/dashboard") ||
    location.pathname.startsWith("/payment"); // ✅ برای صفحه payment/result هم اسلایدر نیاد

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <>
      <Helmet>
        <title>هیئت تکواندو چهارمحال و بختیاری</title>
        <meta
          name="description"
          content="سایت رسمی هیئت تکواندو استان چهارمحال و بختیاری | اطلاعیه‌ها، اخبار، ثبت‌نام بازیکن، مربی و باشگاه"
        />
        <meta
          name="keywords"
          content="هیئت تکواندو شهرکرد ، هیئت تکواندو استان چهارمحال و بختیاری ، تکواندو شهرکرد ،سایت رسمی هیئت تکواندو استان چهارمحال و بختیاری، تکواندو چهارمحال و بختیاری، chbtkd.ir، chbtkd"
        />
      </Helmet>

      {!isSpecialPage && isMobile && (
        <button
          className="slider-toggle-btn"
          onClick={() => setShowSlider((prev) => !prev)}
          aria-label="toggle sliders"
          title="باز/بسته کردن اسلایدر"
        >
          {showSlider ? "×" : "≡"}
        </button>
      )}

      {!isSpecialPage && (
        <div className={`slider ${isMobile && showSlider ? "show-mobile" : ""}`}>
          <section className="slider-section">
            <ImageSlider />
          </section>
          <section className="slider-section">
            <NewsSlider />
          </section>
          <section className="slider-section">
            <CircularSlider />
          </section>
        </div>
      )}

      {!isSpecialPage && <Userpanel />}
    </>
  );
};

function App() {
  return (
    <Router>
      <ScrollToTop />

      <div className="App">
        <Header />

        <main className="main-content">
          <Routes>
            {/* داشبورد + روت‌های تودرتو */}
            <Route
              path="/dashboard/:role"
              element={
                <PrivateRoute>
                  <Dashboard /> {/* داخل Dashboard باید <Outlet/> باشد */}
                </PrivateRoute>
              }
            >
              {/* جزئیات مسابقه */}
              <Route
                path="competitions/:slug"
                element={<CompetitionDetails />}
              />

              {/* جدول مسابقات */}
              <Route
                path="competitions/:slug/bracket"
                element={<CompetitionBracket />}
              />

              {/* ثبت‌نام گروهی مربی (تک/تیمی، کیوروگی یا پومسه) */}
              <Route
                path="competitions/:slug/register/athlete"
                element={<CoachRegisterStudents />}
              />

              {/* ✅ ثبت‌نام تیمی پومسه */}
              <Route
                path="competitions/:slug/register/team"
                element={<PoomsaeTeamRegister />}
              />

              {/* کارت ثبت‌نام تکی */}
              <Route
                path="enrollments/:enrollmentId/card"
                element={<EnrollmentCard />}
              />

              {/* چاپ کارت‌های گروهی */}
              <Route
                path="enrollments/bulk"
                element={<EnrollmentCardsBulk />}
              />

              {/* نتایج مسابقه */}
              <Route
                path="competitions/:slug/results"
                element={<CompetitionResults />}
              />

              {/* دوره/سمینار */}
              <Route path="courses/:slug" element={<SeminarDetail />} />
            </Route>

            {/* ✅ نتیجه پرداخت (برای همهٔ نقش‌ها) */}
            <Route path="/payment/result" element={<PaymentResult />} />

            {/* صفحات محتوا */}
            <Route path="/news/:id" element={<NewsDetail />} />
            <Route path="/circular/:id" element={<CircularDetail />} />

            {/* ثبت‌نام‌ها */}
            <Route path="/register-coach" element={<RegisterCoachPage />} />
            <Route path="/register-player" element={<RegisterplayerPage />} />
            <Route path="/register-club" element={<RegisterClubPage />} />

            {/* صفحه اصلی و fallback */}
            <Route path="/" element={<MainPage />} />
            <Route path="*" element={<MainPage />} />
          </Routes>
        </main>

        <Footer />
      </div>
    </Router>
  );
}

export default App;
