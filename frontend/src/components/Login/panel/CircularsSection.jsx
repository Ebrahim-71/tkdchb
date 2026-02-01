import React, { useEffect, useState } from 'react';
import axios from 'axios';
import PaginatedList from '../../common/PaginatedList';
import CircularCard from './maincontentpanel/CircularCard';

const CircularsSection = () => {
  const [circulars, setCirculars] = useState([]);

  useEffect(() => {
    const role = localStorage.getItem("user_role");
    const token = localStorage.getItem(`${role}_token`);

    axios.get('https://api.chbtkd.ir/api/circulars/', {
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      setCirculars(res.data);
    }).catch((err) => {
      console.error("خطا در دریافت بخشنامه‌ها:", err);
    });
  }, []);

  return (
    <div style={{ padding: "2rem" }}>
      <h2>بخشنامه‌ها</h2>

      <PaginatedList
        items={circulars}
        itemsPerPage={4}
        renderItem={(item) => (
          <div
             style={{
              width: window.innerWidth <= 768 ? "90%" : "44%",
              boxSizing: "border-box",
              margin: "10px 20px",
              display: "inline-flex",
              flexDirection: "column",
              verticalAlign: "top",
            }}
          >
            <CircularCard circular={item} />
          </div>
        )}
      />
    </div>
  );
};

export default CircularsSection;


