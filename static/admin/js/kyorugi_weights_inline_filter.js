(function () {
  function byId(id) { return document.getElementById(id); }

  function selectedIds(selectEl) {
    return new Set(Array.from(selectEl.options).map(o => String(o.value)));
  }

  function allFromSelects() {
    // همه inline های filter_horizontal:
    // id مثل: id_mat_assignments-0-weights_from
    return Array.from(document.querySelectorAll('select[id$="-weights_from"], select#id_weights_from'))
  }

  function toSelectFor(fromEl) {
    return document.getElementById(fromEl.id.replace("_from", "_to"));
  }

  async function refreshAllWeights() {
    const genderEl = byId("id_gender");
    const ageEl = byId("id_age_category");

    const gender = genderEl ? genderEl.value : "";
    const age_category = ageEl ? ageEl.value : "";

    if (!gender) return; // بدون جنسیت فیلتر نکن

    let base = window.location.pathname;

    // اگر /<id>/change/ بود
    base = base.replace(/\/\d+\/change\/$/, "/");
    
    // اگر /add/ بود
    base = base.replace(/\/add\/$/, "/");
    
    const url = base + "weights-options/?gender=" + encodeURIComponent(gender)
      + "&age_category=" + encodeURIComponent(age_category || "");


    const res = await fetch(url, { credentials: "same-origin" });
    const json = await res.json();
    const items = json.results || [];

    allFromSelects().forEach(fromEl => {
      const toEl = toSelectFor(fromEl);
      if (!toEl) return;

      const sel = selectedIds(toEl);

      // پاک کردن Available
      fromEl.options.length = 0;

      // ساخت Available جدید (بدون مواردی که قبلاً انتخاب شده‌اند)
      items.forEach(it => {
        if (!sel.has(String(it.id))) {
          const opt = document.createElement("option");
          opt.value = it.id;
          opt.text = it.text;
          fromEl.add(opt);
        }
      });
    });
  }

  window.addEventListener("load", function () {
    const genderEl = byId("id_gender");
    const ageEl = byId("id_age_category");

    if (genderEl) genderEl.addEventListener("change", refreshAllWeights);
    if (ageEl) ageEl.addEventListener("change", refreshAllWeights);

    refreshAllWeights();
  });
})();
