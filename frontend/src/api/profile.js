// src/api/profile.js
function pickToken() {
  const role = localStorage.getItem("user_role") || "";
  const keys = [`${role}_token`, "both_token", "coach_token", "player_token", "referee_token", "club_token", "access_token"];
  for (const k of keys) { const v = localStorage.getItem(k); if (v) return v; }
  return null;
}

export async function getMyProfile() {
  const token = pickToken();
  const r = await fetch("https://api.chbtkd.ir/api/auth/user-profile-with-form-data/", {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    credentials: "omit",
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "خطا در دریافت پروفایل");

  const p = data.profile || {};
  const coachName = [p.first_name, p.last_name].filter(Boolean).join(" ").trim();

  const clubs = new Set();
  if (p.club && p.club.club_name) clubs.add(p.club.club_name);
  if (Array.isArray(p.coaching_clubs)) p.coaching_clubs.forEach(c => c?.club_name && clubs.add(c.club_name));

  return { coachName, clubNames: Array.from(clubs) };
}
