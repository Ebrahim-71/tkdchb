import React, { useEffect, useState } from "react";
import axios from "axios";
import PaginatedList from "../../../common/PaginatedList";
import "./ChangeCoachClubs.css";

const ChangeCoachClubs = () => {
  const [allClubs, setAllClubs] = useState([]);
  const [selectedClubs, setSelectedClubs] = useState([]);
  const [loading, setLoading] = useState(false);
  const maxSelection = 3;

  useEffect(() => {
    const fetchData = async () => {
      try {
        const role = localStorage.getItem("user_role");
        const token = localStorage.getItem(`${role}_token`);

        const [all, mine] = await Promise.all([
          axios.get("https://api.chbtkd.ir/api/auth/all-clubs/", {
            headers: { Authorization: `Bearer ${token}` }
          }),
          axios.get("https://api.chbtkd.ir/api/auth/coach/clubs/", {
            headers: { Authorization: `Bearer ${token}` }
          })
        ]);

        const mineIds = mine.data.map(club => club.id);
        const sorted = [
          ...all.data.filter(club => mineIds.includes(club.id)),
          ...all.data.filter(club => !mineIds.includes(club.id))
        ];

        setAllClubs(sorted);
        setSelectedClubs(mineIds);
      } catch (err) {
        console.error("خطا در دریافت اطلاعات باشگاه‌ها", err);
      }
    };

    fetchData();
  }, []);

  const toggleClub = (clubId) => {
    setSelectedClubs(prev => {
      if (prev.includes(clubId)) {
        return prev.filter(id => id !== clubId);
      } else if (prev.length < maxSelection) {
        return [...prev, clubId];
      } else {
        alert("حداکثر ۳ باشگاه را می‌توانید انتخاب کنید.");
        return prev;
      }
    });
  };

  const handleSubmit = async () => {
    try {
      setLoading(true);
      const role = localStorage.getItem("user_role");
      const token = localStorage.getItem(`${role}_token`);

      await axios.patch("https://api.chbtkd.ir/api/auth/coach/update-clubs/", {
        coaching_clubs: selectedClubs
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });

      alert("باشگاه‌ها با موفقیت به‌روزرسانی شدند.");
    } catch (err) {
      console.error("خطا در ذخیره باشگاه‌ها", err);
      alert("خطا در ذخیره باشگاه‌ها");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="change-clubs">
      <h2>تغییر باشگاه‌های مربی</h2>

      <div className="clubs-header">
        <div>نام باشگاه</div>
        <div>نام موسس</div>
        <div>انتخاب</div>
      </div>

      <PaginatedList
        items={allClubs}
        itemsPerPage={10}
        renderItem={(club) => (
          <div className="club-row">
            <div>{club.club_name}</div>
            <div>{club.founder_name}</div>
            <div>
              <input
                type="checkbox"
                checked={selectedClubs.includes(club.id)}
                onChange={() => toggleClub(club.id)}
              />
            </div>
          </div>
        )}
      />

      <div className="submit-wrapper">
        <button className="confirm-btn" onClick={handleSubmit} disabled={loading}>
          {loading ? "در حال ذخیره..." : "تأیید"}
        </button>
      </div>
    </div>
  );
};

export default ChangeCoachClubs;
