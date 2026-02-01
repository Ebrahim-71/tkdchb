import React, { useEffect, useState } from 'react';
import axios from 'axios';
import PaginatedList from '../../common/PaginatedList';
import NewsCard from './maincontentpanel/NewsCard.jsx';

const NewsSection = () => {
  const [news, setNews] = useState([]);

  useEffect(() => {
    const role = localStorage.getItem("user_role");
    const token = localStorage.getItem(`${role}_token`);

    axios.get('https://api.chbtkd.ir/api/news/', {
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      setNews(res.data);
    }).catch((err) => {
      console.error("خطا در دریافت اخبار:", err);
    });
  }, []);

  return (
    <div style={{ padding: "2rem" }}>
      <h2>اخبار</h2>

      <PaginatedList
        items={news}
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
            <NewsCard news={item} />
          </div>

        )}
      />
    </div>
  );
};

export default NewsSection;
