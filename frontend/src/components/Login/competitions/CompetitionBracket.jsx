import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getBracket } from "../../../api/competitions";
import "./CompetitionBracket.css";
import boardLogoFile from "../../../assets/img/logo.png";
import { toPng } from "html-to-image"; // npm i html-to-image

// اولویت: env → API → فایل محلی
const BOARD_LOGO = process.env.REACT_APP_BOARD_LOGO_URL || boardLogoFile;

// نام فایل امن
function slugify(s = "") {
  return (
    String(s)
      .trim()
      .replace(/\s+/g, "-")
      .replace(/[^\u0600-\u06FF\w\-]+/g, "")
      .replace(/\-+/g, "-")
      .replace(/^\-+|\-+$/g, "") || "bracket"
  );
}

// DPI منطقی برای سرعت/کیفیت
const SNAPSHOT_DPR = Math.min(1.6, Math.max(1, window.devicePixelRatio || 1));

/* ===================== کارت براکت ===================== */
function BracketCard({ draw, logoUrl = BOARD_LOGO }) {
  // کل محتوای کارت (هدر + بدنه) → منبع اسنپ‌شات
  const contentRef = useRef(null);
  // ریشه‌ی براکت زنده برای پر/فیت
  const wrapRef = useRef(null);
  const viewRef = useRef(null);

  const [png, setPng] = useState(null);
  const [rendering, setRendering] = useState(false);
  const [renderErr, setRenderErr] = useState("");

  // نمایش زمین غالب
  const matNo = useMemo(() => {
    const map = new Map();
    (draw.matches || []).forEach((m) => {
      const mat =
        m?.mat_no ?? m?.mat ?? m?.tatami_no ?? m?.tatami ?? m?.ring ?? m?.area ?? m?.court ?? null;
      if (!mat) return;
      map.set(mat, (map.get(mat) || 0) + 1);
    });
    let best = null, cnt = -1;
    for (const [k, v] of map.entries()) if (v > cnt) { best = k; cnt = v; }
    return best || "—";
  }, [draw.matches]);

  /* ---- پر کردن برد + فیت داخل کارت ---- */
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;

    const matches = draw.matches || [];

    const applyRoundShifting = (declaredSize) => {
      const size = Math.max(1, Number(declaredSize || 0));
      let roundsCount = 0; while ((1 << roundsCount) < size) roundsCount++;
      roundsCount = Math.max(1, roundsCount);
      const SHIFT = 5 - roundsCount;
      for (let c = 1; c <= 5; c++) {
        const col = wrap.querySelector(".r" + c);
        if (col) col.style.display = c < SHIFT + 1 ? "none" : "";
      }
      return { mapRound: (r) => r + SHIFT };
    };

    const fitToCard = () => {
      const view  = wrap.querySelector(".view");
      const board = wrap.querySelector(".board");
      if (!view || !board) return;
      board.style.transform = "translateX(-50%) scale(1)";
      const pad = 6;
      const naturalW = board.scrollWidth + pad;
      const naturalH = board.scrollHeight + pad;
      const vw = view.clientWidth, vh = view.clientHeight;
      const scale = Math.min(vw / naturalW, vh / naturalH) * 0.985;
      board.style.setProperty("--scale", Math.max(0, Math.min(1, scale)).toFixed(3));
      board.style.transform = "";
    };

    const isRest = (v) => String(v || "").trim() === "استراحت";
    const nonEmpty = (v) => String(v || "").trim() !== "";
    const put = (el, val) => {
      if (!el) return;
      el.value = val || "";
      el.title = el.value;
      if (isRest(el.value)) el.classList.add("bye");
      else el.classList.remove("bye");
    };

   const getMatchNumber = (m) => {
    // پشتیبانی از بیشترین نام‌های رایج سمت بک‌اند
    const candidates = [
      "match_number","number","match_no","no","bout_no",
      "number_on_mat","order_on_mat","seq_on_mat",
      "seq_no","seq","order","index","bracket_no"
    ];
    for (const k of candidates) {
      if (m?.[k] !== undefined && m?.[k] !== null && m?.[k] !== "") return m[k];
    }
    return "";
  };
    const firstRoundInfo = (mapRound) => {
      for (let r = 1; r <= 5; r++) {
        const vr = mapRound(r);
        const count = wrap.querySelectorAll(`input.player-input[data-r="${vr}"][data-pos="a"]`).length;
        if (count > 0) return { r, vr, count };
      }
      return { r: null, vr: null, count: 0 };
    };

    const propagateByesOneStep = (mapRound) => {
      const info = firstRoundInfo(mapRound);
      if (!info.r) return;
      const r = info.r, vr = info.vr, count = info.count;

      for (let i = 0; i < count; i++) {
        const a = wrap.querySelector(`input.player-input[data-r="${vr}"][data-i="${i}"][data-pos="a"]`);
        const b = wrap.querySelector(`input.player-input[data-r="${vr}"][data-i="${i}"][data-pos="b"]`);
        const n = wrap.querySelector(`input.bubble[data-r="${vr}"][data-i="${i}"][data-num]`);

        const restPair = (String(a?.value).trim() === "استراحت") ^ (String(b?.value).trim() === "استراحت");
        if (restPair && n) { n.classList.add("bye-mark"); n.value = ""; n.title = "استراحت"; }

        const hasA = a && String(a.value || "").trim() !== "" && String(a.value || "").trim() !== "استراحت";
        const hasB = b && String(b.value || "").trim() !== "" && String(b.value || "").trim() !== "استراحت";
        if (!((hasA && String(b?.value).trim() === "استراحت") || (hasB && String(a?.value).trim() === "استراحت"))) continue;

        const winner = hasA ? a.value : b.value;
        const nextVr = mapRound(r + 1);
        if (!wrap.querySelector(`input.player-input[data-r="${nextVr}"]`)) continue;
        const nextI = Math.floor(i / 2);
        const nextPos = i % 2 === 0 ? "a" : "b";
        const nxt = wrap.querySelector(`input.player-input[data-r="${nextVr}"][data-i="${nextI}"][data-pos="${nextPos}"]`);
        if (nxt && (String(nxt.value || "").trim() === "" || String(nxt.value || "").trim() === "استراحت")) put(nxt, winner);
      }
    };

    const detectSinglePlayerName = (ms) => {
      const s = new Set();
      for (const m of ms) {
        const a = (m.player_a_name || "").trim(); if (a && a !== "استراحت") s.add(a);
        const b = (m.player_b_name || "").trim(); if (b && b !== "استراحت") s.add(b);
      }
      return s.size === 1 ? [...s][0] : "";
    };

    const fillSinglePathAllTheWay = (name, mapRound, firstInfo) => {
      if (!name || !firstInfo || !firstInfo.r) return;
      let i = 0;
      for (let idx = 0; idx < firstInfo.count; idx++) {
        const a = wrap.querySelector(`input.player-input[data-r="${firstInfo.vr}"][data-i="${idx}"][data-pos="a"]`);
        const b = wrap.querySelector(`input.player-input[data-r="${firstInfo.vr}"][data-i="${idx}"][data-pos="b"]`);
        if (a?.value.trim() === name || b?.value.trim() === name) { i = idx; break; }
      }
      let r = firstInfo.r;
      while (true) {
        const vr = mapRound(r);
        const a = wrap.querySelector(`input.player-input[data-r="${vr}"][data-i="${i}"][data-pos="a"]`);
        const b = wrap.querySelector(`input.player-input[data-r="${vr}"][data-i="${i}"][data-pos="b"]`);
        const n = wrap.querySelector(`input.bubble[data-r="${vr}"][data-i="${i}"][data-num]`);
        if (!a || !b) break;

        if (vr === firstInfo.vr) {
          if (a.value.trim() === name) put(b, "استراحت");
          else if (b.value.trim() === name) put(a, "استراحت");
          else { put(a, name); put(b, "استراحت"); }
          if (n) { n.classList.add("bye-mark"); n.value = ""; n.title = "استراحت"; }
        }

        const nextVr = mapRound(r + 1);
        if (!wrap.querySelector(`input.player-input[data-r="${nextVr}"]`)) break;
        const nextI = Math.floor(i / 2);
        const nextPos = i % 2 === 0 ? "a" : "b";
        const nxt = wrap.querySelector(`input.player-input[data-r="${nextVr}"][data-i="${nextI}"][data-pos="${nextPos}"]`);
        if (nxt) put(nxt, name);

        i = nextI;
        r += 1;
      }

      const champ = wrap.querySelector(".r6 .champ .player-input");
      if (champ) { champ.value = `🏆  ${name}`; champ.title = name; }
    };

    const declaredSize = draw.size || (draw.matches ? Math.max(1, draw.matches.length * 2) : 1);
    const { mapRound } = applyRoundShifting(declaredSize);
    const fr = firstRoundInfo(mapRound);

    if (matches.length) {
      const byRound = new Map();
      for (const m of matches) {
        const r = Number(m.round_no ?? m.round ?? m.stage ?? 1);
        if (!byRound.has(r)) byRound.set(r, []);
        byRound.get(r).push(m);
      }
      for (const [r, arr] of byRound) {
      // اولویت با slot_a، بعد order_in_round، بعد index عمومی:
      arr.sort((a, b) => {
        const ka = a.slot_a ?? a.order_in_round ?? a.index ?? 0;
        const kb = b.slot_a ?? b.order_in_round ?? b.index ?? 0;
        return (ka || 0) - (kb || 0);
      });
      // Fallback: اگر هیچ numberای نیامده بود، یک شماره‌ی ترتیبی موقت بگذار تا کاربر علامت‌ها را ببیند
      let local = 1;
      arr.forEach(m => { if (!getMatchNumber(m)) m.__fallback_no__ = local++; });
    }

      for (const [r, arr] of byRound) {
        const vr = mapRound(r);
        const isFirstRound = vr === fr.vr;

        arr.forEach((m, idx) => {
          const a = wrap.querySelector(`input.player-input[data-r="${vr}"][data-i="${idx}"][data-pos="a"]`);
          const b = wrap.querySelector(`input.player-input[data-r="${vr}"][data-i="${idx}"][data-pos="b"]`);
          const n = wrap.querySelector(`input.bubble[data-r="${vr}"][data-i="${idx}"][data-num]`);

          const pa = m.player_a_name ?? m.a_name ?? m.player_a ?? "";
          const pb = m.player_b_name ?? m.b_name ?? m.player_b ?? "";
          const hasA = pa.trim() !== "";
          const hasB = pb.trim() !== "";

          if (a) a.value = hasA ? pa : (hasB && m.is_bye && isFirstRound ? "استراحت" : a.value);
          if (b) b.value = hasB ? pb : (hasA && m.is_bye && isFirstRound ? "استراحت" : b.value);

          if (n) {
            const restPair = isFirstRound && ((a?.value?.trim() === "استراحت") ^ (b?.value?.trim() === "استراحت"));
            if (restPair) { n.classList.add("bye-mark"); n.value = ""; n.title = "استراحت"; }
              else {
              n.classList.remove("bye-mark");
              const no = getMatchNumber(m) || m.__fallback_no__ || "";
              n.value = String(no);
              n.title = n.value;
            }
          }
        });
      }
    }

    const singleName = detectSinglePlayerName(matches);
    if (singleName) fillSinglePathAllTheWay(singleName, mapRound, fr);
    else propagateByesOneStep(mapRound);

    fitToCard();
    let tid;
    const onResize = () => { clearTimeout(tid); tid = setTimeout(() => { fitToCard(); fitHeader(); }, 120); };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [draw]);

  /* ---- اسکیل خودکار هدر تا همه پِل‌ها در یک خط بمانند ---- */
  const fitHeader = useCallback(() => {
    const root = contentRef.current; if (!root) return;
    const hd = root.querySelector(".hd"); if (!hd) return;
    const left = hd.querySelector(".left"); const logo = hd.querySelector(".brand-logo");
    const avail = hd.clientWidth - (logo?.offsetWidth || 0) - 24; // فاصله سمت لوگو
    const need = left.scrollWidth;
    let scale = 1;
    if (need > avail) scale = Math.max(0.85, Math.min(1, avail / need));
    root.style.setProperty("--hdrScale", scale.toFixed(3));
  }, []);

  /* ---- اسنپ‌شات از کل محتوای کارت (هدر + بدنه) ---- */
  const renderToImage = useCallback(async () => {
    const node = contentRef.current;
    if (!node) return;

    setRendering(true);
    setRenderErr("");
    node.classList.add("is-snapshotting");

    // چیدمان نهایی + فونت‌ها
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    try { if (document.fonts?.ready) await document.fonts.ready; } catch {}

    // قبل از اسنپ‌شات، هدر را فیت کن
    fitHeader();

    try {
      const dataUrl = await toPng(node, {
        pixelRatio: SNAPSHOT_DPR,
        backgroundColor: "#fff",
        cacheBust: true,
        filter: (n) => {
          if (n?.classList?.contains?.("snapshot-overlay")) return false;
          return true;
        },
      });
      setPng(dataUrl);
    } catch (e) {
      setRenderErr("ساخت تصویر ناموفق (CORS یا DOM سنگین).");
    } finally {
      node.classList.remove("is-snapshotting");
      setRendering(false);
    }
  }, [fitHeader]);

  // یک بار خودکار بعد از پرشدن جدول
  useEffect(() => {
    const t = setTimeout(() => { fitHeader(); renderToImage(); }, 140);
    return () => clearTimeout(t);
  }, [renderToImage, fitHeader]);

  const filename =
    `${slugify(draw.age_category_name)}-${slugify(draw.gender_display)}-` +
    `${slugify(draw.belt_group_label)}-${slugify(draw.weight_name)}-${slugify(matNo)}.png`;

  const downloadOne = () => {
    if (!png) return;
    const a = document.createElement("a");
    a.href = png;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const showSnapshot = !!png && !rendering && !renderErr;

  return (
    <div className={`card ${showSnapshot ? "is-snap" : ""} ${rendering ? "is-rendering" : ""}`} data-filename={filename}>
      {/* --- محتوای کارت (هدر + بدنه) = منبع اسنپ‌شات --- */}
      <div className="card-content" ref={contentRef}>
        <div className="hd">
          <div className="left">
            <span className="pill">{draw.age_category_name || "—"}</span>
            <span className="pill">{draw.gender_display || "—"}</span>
            <span className="pill">رده کمربندی: {draw.belt_group_label || "—"}</span>
            <span className="pill">رده وزنی: {draw.weight_name || "—"}</span>
            <span className="pill">زمین: <b>{matNo}</b></span>
          </div>

          <img
            className="brand-logo"
            src={logoUrl || boardLogoFile}
            alt="لوگوی هیئت"
            crossOrigin="anonymous"
            onError={(e) => { e.currentTarget.src = boardLogoFile; }}
          />
        </div>

        <div className="bd">
          {/* نسخه زنده براکت */}
          <div className="bracket-wrap" data-size={draw.size || ""} ref={wrapRef}>
            <div className="view" ref={viewRef}>
              <div className="board">
                {/* R1 */}
                <div className="col r1">
                  <div className="stack">
                    {Array.from({ length: 16 }).map((_, i) => (
                      <React.Fragment key={"r1-" + i}>
                        <div className="item">
                          <input className="player-input" data-r="1" data-i={i} data-pos="a" readOnly />
                        </div>
                        <div className="item">
                          <input className="player-input" data-r="1" data-i={i} data-pos="b" readOnly />
                          <input className="bubble" data-r="1" data-i={i} data-num readOnly style={{ right: "-28px" }} />
                        </div>
                      </React.Fragment>
                    ))}
                  </div>
                </div>

                {/* R2 */}
                <div className="col r2">
                  <div className="stack">
                    {Array.from({ length: 8 }).map((_, i) => (
                      <React.Fragment key={"r2-" + i}>
                        <div className="item">
                          <input className="player-input" data-r="2" data-i={i} data-pos="a" readOnly />
                        </div>
                        <div className="item">
                          <input className="player-input" data-r="2" data-i={i} data-pos="b" readOnly />
                          <input className="bubble" data-r="2" data-i={i} data-num readOnly style={{ right: "-28px" }} />
                        </div>
                      </React.Fragment>
                    ))}
                  </div>
                </div>

                {/* R3 */}
                <div className="col r3">
                  <div className="stack">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <React.Fragment key={"r3-" + i}>
                        <div className="item">
                          <input className="player-input" data-r="3" data-i={i} data-pos="a" readOnly />
                        </div>
                        <div className="item">
                          <input className="player-input" data-r="3" data-i={i} data-pos="b" readOnly />
                          <input className="bubble" data-r="3" data-i={i} data-num readOnly style={{ right: "-28px" }} />
                        </div>
                      </React.Fragment>
                    ))}
                  </div>
                </div>

                {/* R4 */}
                <div className="col r4">
                  <div className="stack">
                    {Array.from({ length: 2 }).map((_, i) => (
                      <React.Fragment key={"r4-" + i}>
                        <div className="item">
                          <input className="player-input" data-r="4" data-i={i} data-pos="a" readOnly />
                        </div>
                        <div className="item">
                          <input className="player-input" data-r="4" data-i={i} data-pos="b" readOnly />
                          <input className="bubble" data-r="4" data-i={i} data-num readOnly style={{ right: "-28px" }} />
                        </div>
                      </React.Fragment>
                    ))}
                  </div>
                </div>

                {/* R5 (Final) */}
                <div className="col r5">
                  <div className="stack">
                    <div className="item">
                      <input className="player-input" data-r="5" data-i="0" data-pos="a" readOnly />
                    </div>
                    <div className="item">
                      <input className="player-input" data-r="5" data-i="0" data-pos="b" readOnly />
                      <input className="bubble" data-r="5" data-i="0" data-num readOnly style={{ right: "-18px" }} />
                    </div>
                  </div>
                </div>

                {/* Champion */}
                <div className="col r6">
                  <div className="champ">
                    <input className="player-input" defaultValue="🏆                      " readOnly />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div> {/* /card-content */}

      {/* تصویرِ تمام‌کارت (فقط وقتی آماده شد) */}
      {png && !rendering && !renderErr && (
        <img className="card-snapshot" src={png} alt="Bracket snapshot" />
      )}

      {/* اورلی انتظار */}
      {rendering && (
        <div className="snapshot-overlay" aria-hidden="true">
          <div className="spinner" />
          <div className="wait-label">در حال ساخت تصویر…</div>
        </div>
      )}

      {/* فقط دکمهٔ دانلود (چاپ و بازسازی حذف شدند) */}
      <div className="card-controls">
        <button className="btn btn-primary" onClick={downloadOne} disabled={!png || rendering}>
          دانلود تصویر
        </button>
        {renderErr && <span className="err">{renderErr}</span>}
      </div>
    </div>
  );
}

/* ===================== صفحه‌ی براکت ===================== */
export default function CompetitionBracket() {
  const { slug, role } = useParams();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setErr(null);
    getBracket(slug)
      .then((res) => { if (mounted) setData(res); })
      .catch((e) => { if (mounted) setErr(e); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [slug]);

  const goDetails = () =>
    navigate(`/dashboard/${encodeURIComponent(role)}/competitions/${encodeURIComponent(slug)}`);

  const downloadAll = () => {
    const imgs = document.querySelectorAll(".card-snapshot");
    if (!imgs.length) return;
    imgs.forEach((img, idx) => {
      const a = document.createElement("a");
      const name = img.closest(".card")?.dataset?.filename || `bracket-${idx + 1}.png`;
      a.href = img.getAttribute("src");
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
    });
  };

  if (loading) return <div className="cb-wrap">در حال بارگذاری…</div>;

  if (err) {
    const is404 = err?.status === 404;
    return (
      <div className="cb-wrap cb-error" dir="rtl">
        <div style={{ marginBottom: 12 }}>
          {is404 ? "هنوز قرعه‌کشی یا انتشار جدول انجام نشده است." : (err.message || "خطا در دریافت جدول")}
        </div>
        <div className="cb-toolbar">
          <button className="btn btn-secondary" onClick={goDetails}>بازگشت به جزئیات</button>
        </div>
      </div>
    );
  }

  const draws = Array.isArray(data?.draws) ? data.draws : [];
  if (!draws.length) {
    return (
      <div className="cb-wrap" dir="rtl">
        <div className="cb-empty">هنوز قرعه‌کشی انجام نشده یا شماره‌گذاری کامل نیست.</div>
        <div className="cb-toolbar">
          <button className="btn btn-secondary" onClick={goDetails}>بازگشت به جزئیات</button>
        </div>
      </div>
    );
  }

  const logoUrl =
    data?.board_logo_url || data?.board_logo || data?.logo_url || data?.logo || BOARD_LOGO;

  return (
    <div className="cb-wrap" dir="rtl">
      <div className="cb-toolbar">
        <button className="btn btn-secondary" onClick={goDetails}>بازگشت</button>
        <button className="btn btn-outline" onClick={downloadAll}>دانلود همه تصاویر</button>
      </div>

      <div className="cards">
        {draws.map((d) => (
          <BracketCard key={d.id} draw={d} logoUrl={logoUrl} />
        ))}
      </div>
    </div>
  );
}
