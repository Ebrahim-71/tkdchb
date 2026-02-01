import React, { useEffect, useState } from 'react';
import PaginatedList from '../../common/PaginatedList';
import { useNavigate } from 'react-router-dom';
import PersonalInfoForm from '../panel/maincontentpanel/PersonalInfoForm'; // این خط مهمه
import "./dashboard.css";

const MainContent = ({ selectedSection }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const role = localStorage.getItem("user_role");
  const token = localStorage.getItem(`${role}_token`);

  const endpoints = {
    matches: `https://api.chbtkd.ir/api/dashboard/${role}/matches/`,
    exams: `https://api.chbtkd.ir/api/dashboard/${role}/exams/`,
    courses: `https://api.chbtkd.ir/api/dashboard/${role}/courses/`,
    circulars: `https://api.chbtkd.ir/api/dashboard/${role}/circulars/`,
    news: `https://api.chbtkd.ir/api/dashboard/${role}/news/`,
    profile: `https://api.chbtkd.ir/api/auth/dashboard/${role}/`,
  };

  const fetchData = async () => {
    if (!selectedSection || !role || !token) {
      setError('دسترسی نامعتبر. لطفاً دوباره وارد شوید.');
      return;
    }

    const url = endpoints[selectedSection];
    if (!url) {
      setError('یک گزینه انتخاب کنید');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (res.status === 401) {
        localStorage.removeItem(`${role}_token`);
        localStorage.removeItem("user_role");
        setError("دسترسی غیرمجاز. لطفاً دوباره وارد شوید.");
        navigate("/");
        return;
      }

      const data = await res.json();
      setItems(Array.isArray(data) ? data : [data]);
    } catch (err) {
      console.error("Fetch error:", err);
      setError("خطا در دریافت اطلاعات.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedSection && selectedSection !== "profile") {
      fetchData();
    }
  }, [selectedSection]);

  if (!selectedSection) return <div className="maincontent">یک بخش را انتخاب کنید</div>;
  if (loading) return <div className="main-content">در حال بارگذاری...</div>;
  if (error) return <div className="main-content error-msg">{error}</div>;

  // 🔹 اگر بخش پروفایل انتخاب شده، فرم رو نمایش بده
  if (selectedSection === "profile") {
    return (
      <div className="main-content">
        <PersonalInfoForm />
      </div>
    );
  }

  const renderItem = (item) => (
    <div className="item-card">
      <h4>{item.title || "بدون عنوان"}</h4>
      <p>{item.description || item.summary || "بدون توضیح"}</p>
    </div>
  );

  return (
    <div className="main-content">
      <PaginatedList items={items} renderItem={renderItem} itemsPerPage={3} />
    </div>
  );
};

export default MainContent;
