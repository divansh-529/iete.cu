import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { BrandLogo } from "../../components/Brand";
import { cx } from "../../components/ui";

/** The public front page. Everything here is plain content: edit the lists below to update it. */
const CONTACT = {
  email: "iete.cu@cumail.in",
  phone: "+91 98120 69412",
  phoneHref: "tel:+919812069412",
  instagram: "https://www.instagram.com/iete.cu/",
  instagramHandle: "@iete.cu",
  linkedin: "https://lnkd.in/p/gUGRv8wu",
};

const JOIN_URL = "https://www.cuchd.in/iete/";

const NAV = [["about", "About"], ["why", "Why join"], ["events", "Events"], ["faculty", "Faculty"], ["contact", "Contact"]] as const;

const STATS = [
  { value: 1953, suffix: "", label: "IETE founded", plain: true },
  { value: 60, suffix: "+", label: "IETE centres across India" },
  { value: 1.25, suffix: " lakh+", label: "IETE members", decimals: 2 },
  { value: 4, suffix: "", label: "Forum milestones since launch" },
];

const TERMINAL = [
  "$ whoami",
  "IETE Student Forum, Chandigarh University",
  "$ cat parent_society.txt",
  "The Institution of Electronics and Telecommunication Engineers.",
  "One of India's leading professional societies since 1953.",
  "$ cat our_story.txt",
  "Inaugurated by the Department of CSE on 20 April 2026.",
  "Recruitment drive. AI innovation challenge. Multi-college hackathon.",
  "$ ./join --now",
];

const BENEFITS = [
  { title: "Build real-world skills", text: "Learn by doing: run events, solve real problems and work with real deadlines.", icon: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5" },
  { title: "Work with an amazing team", text: "Find people who care about the same things you do, across every year and branch.", icon: "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6m13 9v-1a4 4 0 0 0-3-3.9M16 4.1a3 3 0 0 1 0 5.8" },
  { title: "Lead projects and events", text: "Go from helping out to running the show, with faculty guidance behind you.", icon: "M4 21V5m0 0c4-3 8 3 12 0v9c-4 3-8-3-12 0" },
  { title: "Boost your portfolio", text: "Leave with work you can point to, and a story for your resume and interviews.", icon: "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2m0 9 2 2 4-4" },
  { title: "Network with experts", text: "Meet faculty, industry guests and students from other societies and colleges.", icon: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18m-9-9h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3" },
  { title: "Earn recognition", text: "Certificates and recognition for the people who make things happen.", icon: "M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12m-3.5-1L7 22l5-3 5 3-1.5-8" },
];

const EVENTS = [
  { name: "The Inauguration", when: "20 April 2026", tag: "SYSTEM ONLINE", photo: "/events/inauguration.jpg",
    alt: "Faculty and a full auditorium of students at the IETE Student Forum inauguration",
    text: "The Department of CSE launched the IETE Student Forum with experts from CSIR-CSIO, Chandigarh, and a keynote by Dr. Ritesh Kumar of the IETE Executive Committee.",
    points: ["Guests from CSIR-CSIO", "Faculty and students felicitated"] },
  { name: "Aarohan'26", when: "14 August 2026", tag: "RISE. LEARN. LEAD.", photo: "/events/aarohan.jpg",
    alt: "Students at Aarohan'26 in the C1 Seminar Hall",
    text: "Our recruitment event filled the C1 Seminar Hall with students ready to join the team, from design and content to technical and public relations.",
    points: ["8 teams to join", "Interviews on the day"] },
  { name: "BharatX: AI Innovation Arena", when: "16–17 September 2026", tag: "BUILD WITH AI", photo: "/events/bharatx.jpg",
    alt: "Faculty and a packed hall of students at BharatX: AI Innovation Arena",
    text: "A two-day AI innovation challenge: build with AI, solve real problems and create a stronger Bharat. Teams of up to three competed for trophies.",
    points: ["Up to 65 teams", "E-certificates for everyone"] },
  { name: "CodeYudh 2026", when: "The Battle of Codes", tag: "HACKATHON", photo: "/events/codeyudh.jpg",
    alt: "Winning teams, faculty and guests on stage with prize cheques at CodeYudh 2026",
    text: "We volunteered alongside Alexa Dev, GeeksforGeeks, CSI and IDC at this multi-college hackathon, with winners from Chandigarh University, IIIT Nagpur and REC Banda.",
    points: ["₹1,03,000 in prizes", "Run with partner societies"] },
];

const TEAMS = ["Graphic Design", "Content Writing", "Social Media", "Videography", "Photography", "Technical", "Anchoring & Hosting", "Public Relations"];

/** To add a photo: save a square picture in public/faculty/ and set `photo`. Without one, initials show. */
const FACULTY: { name: string; role: string; url: string; photo?: string }[] = [
  { name: "Dr. Navpreet Kaur Walia", role: "Assistant Director, CSE", url: "https://www.linkedin.com/in/dr-navpreet-kaur-walia-36683922b/", photo: "/faculty/navpreet-kaur-walia.jpg" },
  { name: "Dr. Jasneet Kaur", role: "Head of Department, CSE", url: "https://www.linkedin.com/in/dr-jasneet-kaur-12ba56223/", photo: "/faculty/jasneet-kaur.jpg" },
  { name: "Dr. Parveen Kumar Bajaj", role: "Faculty Advisor, IETE Student Forum", url: "https://www.linkedin.com/in/dr-parveen-bajaj-276b2638/", photo: "/faculty/parveen-kumar-bajaj.jpg" },
  { name: "Shanu Khare", role: "Administrative Officer, CSE", url: "https://www.linkedin.com/in/shanu-khare-04b9191ba/", photo: "/faculty/shanu-khare.jpg" },
  { name: "Anamika L.", role: "Events Team, CSE", url: "https://www.linkedin.com/in/anamika-l-79139b1b8/", photo: "/faculty/anamika-l.jpg" },
  { name: "Sharandeep Kaur", role: "Events Team, CSE", url: "https://www.linkedin.com/in/sharandeep-kaur-b11005341/", photo: "/faculty/sharandeep-kaur.jpg" },
  { name: "Azhar Ashraf Gadoo", role: "Technical Coordinator, CSE", url: "https://www.linkedin.com/in/azhar-ashraf-gadoo-15b41922b/", photo: "/faculty/azhar-ashraf-gadoo.jpg" },
  { name: "Vishal Sharma", role: "Events Team, CSE", url: "https://www.linkedin.com/in/vishal-sharma-51b0a0148/", photo: "/faculty/vishal-sharma.jpg" },
];

function initials(name: string) {
  return name.replace(/^Dr\.\s*/, "").split(/\s+/).slice(0, 2).map((w) => w[0]).join("");
}

function reducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Runs once when the element first scrolls into view. */
function useInView<T extends Element>(threshold = 0.15) {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setSeen(true);
        observer.disconnect();
      }
    }, { threshold });
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);
  return [ref, seen] as const;
}

/** A network of drifting points behind the whole page. Lines reach out to the mouse. */
function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const still = reducedMotion();
    const mouse = { x: -9999, y: -9999 };
    let points: { x: number; y: number; vx: number; vy: number; gold: boolean }[] = [];
    let width = 0;
    let height = 0;
    let frame = 0;

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      // Phones get fewer points and a sharper limit, so scrolling stays smooth.
      const small = width < 768;
      const scale = small ? 1 : Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = width * scale;
      canvas.height = height * scale;
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      const count = small ? 34 : Math.min(110, Math.round((width * height) / 14000));
      points = Array.from({ length: count }, (_, i) => ({
        x: Math.random() * width, y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.45, vy: (Math.random() - 0.5) * 0.45, gold: i % 9 === 0,
      }));
      draw();
    };

    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        for (let j = i + 1; j < points.length; j++) {
          const q = points[j];
          const dist = Math.hypot(p.x - q.x, p.y - q.y);
          if (dist < 130) {
            ctx.strokeStyle = `rgba(93,160,255,${0.22 * (1 - dist / 130)})`;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.stroke();
          }
        }
        const toMouse = Math.hypot(p.x - mouse.x, p.y - mouse.y);
        if (toMouse < 190) {
          ctx.strokeStyle = `rgba(251,191,36,${0.5 * (1 - toMouse / 190)})`;
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(mouse.x, mouse.y);
          ctx.stroke();
        }
        ctx.fillStyle = p.gold ? "rgba(251,191,36,.95)" : "rgba(125,190,255,.85)";
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.gold ? 2.2 : 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const tick = () => {
      if (!document.hidden) {
        for (const p of points) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0 || p.x > width) p.vx *= -1;
          if (p.y < 0 || p.y > height) p.vy *= -1;
        }
        draw();
      }
      frame = requestAnimationFrame(tick);
    };
    const onMove = (e: globalThis.PointerEvent) => {
      if (e.pointerType !== "mouse") return;
      mouse.x = e.clientX;
      mouse.y = e.clientY;
      document.documentElement.style.setProperty("--home-x", `${e.clientX}px`);
      document.documentElement.style.setProperty("--home-y", `${e.clientY}px`);
    };

    resize();
    window.addEventListener("resize", resize);
    if (!still) {
      window.addEventListener("pointermove", onMove, { passive: true });
      frame = requestAnimationFrame(tick);
    }
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);
  return <canvas ref={canvasRef} className="pointer-events-none fixed inset-0 -z-10 size-full" aria-hidden="true" />;
}

const GLYPHS = "!<>-_\\/[]{}=+*^?#01";

/** Text that decodes from random characters into the real words. */
function Scramble({ text, className, delay = 0, start = true }: { text: string; className?: string; delay?: number; start?: boolean }) {
  const [shown, setShown] = useState(text);
  useEffect(() => {
    if (!start || reducedMotion()) {
      setShown(text);
      return;
    }
    let frame = 0;
    const began = performance.now() + delay;
    const tick = (now: number) => {
      const elapsed = now - began;
      const revealed = Math.floor(elapsed / 42);
      setShown(text.split("").map((c, i) => (c === " " || i < revealed ? c : GLYPHS[Math.floor(Math.random() * GLYPHS.length)])).join(""));
      if (revealed < text.length) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text, delay, start]);
  return <span className={className} aria-label={text} role="text">{shown}</span>;
}

function Reveal({ children, className, delay = 0, from = "up" }: { children: ReactNode; className?: string; delay?: number; from?: "up" | "left" | "right" | "zoom" }) {
  const [ref, seen] = useInView<HTMLDivElement>(0.12);
  return (
    <div ref={ref} style={{ transitionDelay: `${delay}ms` }} className={cx("home-reveal", `home-reveal-${from}`, seen && "home-seen", className)}>
      {children}
    </div>
  );
}

/** A card that leans towards the mouse, with a glow that follows it. */
function Tilt({ children, className }: { children: ReactNode; className?: string }) {
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (e.pointerType !== "mouse" || reducedMotion()) return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - box.left) / box.width;
    const y = (e.clientY - box.top) / box.height;
    e.currentTarget.style.setProperty("--rx", `${(0.5 - y) * 14}deg`);
    e.currentTarget.style.setProperty("--ry", `${(x - 0.5) * 14}deg`);
    e.currentTarget.style.setProperty("--mx", `${x * 100}%`);
    e.currentTarget.style.setProperty("--my", `${y * 100}%`);
  };
  const leave = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.style.setProperty("--rx", "0deg");
    e.currentTarget.style.setProperty("--ry", "0deg");
  };
  return <div onPointerMove={move} onPointerLeave={leave} className={cx("home-tilt", className)}>{children}</div>;
}

function CountUp({ value, suffix, decimals = 0, plain }: { value: number; suffix: string; decimals?: number; plain?: boolean }) {
  const [ref, seen] = useInView<HTMLSpanElement>(0.4);
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!seen) return;
    if (reducedMotion()) {
      setShown(value);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min((now - start) / 1600, 1);
      setShown(value * (1 - (1 - t) ** 3));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [seen, value]);
  const text = decimals ? shown.toFixed(decimals) : plain ? String(Math.round(shown)) : Math.round(shown).toLocaleString("en-IN");
  return <span ref={ref} className="tabular-nums">{text}{suffix}</span>;
}

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
         aria-hidden="true" className={className}><path d={d} /></svg>
  );
}

function SectionTitle({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  const [ref, seen] = useInView<HTMLDivElement>(0.3);
  return (
    <div ref={ref} className="mx-auto mb-14 max-w-3xl text-center">
      <p className="home-mono text-sm tracking-[0.25em] text-cyan-300">// {eyebrow}</p>
      <h2 className="home-heading mt-4 text-4xl font-bold text-white sm:text-5xl"><Scramble text={title} start={seen} /></h2>
      {text && <p className={cx("mt-5 text-base text-slate-300 transition-opacity duration-1000 sm:text-lg", seen ? "opacity-100" : "opacity-0")}>{text}</p>}
    </div>
  );
}

function Header() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 24);
      const room = document.documentElement.scrollHeight - window.innerHeight;
      if (bar.current) bar.current.style.transform = `scaleX(${room > 0 ? window.scrollY / room : 0})`;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <header className={cx("fixed inset-x-0 top-0 z-40 transition-colors duration-300", scrolled || open ? "bg-[#060914]/85 backdrop-blur-md" : "bg-transparent")}>
      <div ref={bar} className="home-progress absolute inset-x-0 bottom-0 h-0.5 origin-left scale-x-0" />
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <a href="#top" className="home-logo rounded-lg bg-white px-2 py-1" aria-label="IETE Student Forum, back to top"><BrandLogo className="w-32 sm:w-40" /></a>
        <nav className="hidden items-center gap-1 lg:flex" aria-label="Main">
          {NAV.map(([id, label]) => <a key={id} href={`#${id}`} className="home-navlink rounded-lg px-3 py-2 text-sm font-medium text-slate-200 hover:text-white">{label}</a>)}
          <Link to="/login" className="home-button-outline ml-2 rounded-lg px-4 py-2 text-sm font-semibold text-amber-200">Team portal</Link>
        </nav>
        <button className="rounded-lg p-2 text-white lg:hidden" onClick={() => setOpen((o) => !o)} aria-label="Toggle menu" aria-expanded={open}>
          <Icon d={open ? "M6 6l12 12M18 6 6 18" : "M4 7h16M4 12h16M4 17h16"} className="size-6" />
        </button>
      </div>
      {open && (
        <nav className="border-t border-white/10 px-4 pb-4 lg:hidden" aria-label="Mobile">
          {NAV.map(([id, label]) => <a key={id} href={`#${id}`} onClick={() => setOpen(false)} className="block rounded-lg px-3 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/10">{label}</a>)}
          <Link to="/login" className="mt-2 block rounded-lg bg-amber-400 px-3 py-2.5 text-center text-sm font-semibold text-slate-950">Team portal</Link>
        </nav>
      )}
    </header>
  );
}

/** The IETE triangle as a machine: it draws itself, then pulses inside spinning rings. */
function Reactor({ className }: { className?: string }) {
  return (
    <div className={cx("home-reactor", className)} aria-hidden="true">
      <div className="home-ring home-ring-a" />
      <div className="home-ring home-ring-b" />
      <div className="home-ring home-ring-c" />
      <svg viewBox="0 0 200 180" fill="none" className="absolute inset-[21%] overflow-visible">
        <path className="home-draw" pathLength="1" d="M100 6 194 174H6Z" stroke="#7dd3fc" strokeWidth="2.5" strokeLinejoin="round" />
        <path className="home-draw home-draw-2" pathLength="1" d="M100 34 170 158H30Z" stroke="#fbbf24" strokeWidth="1.5" strokeLinejoin="round" />
        <circle className="home-draw home-draw-3" pathLength="1" cx="100" cy="114" r="31" stroke="#7dd3fc" strokeWidth="2" />
        <text x="100" y="122" textAnchor="middle" className="home-pulse-text" fill="#fff" fontSize="21" fontWeight="700" letterSpacing="1">IETE</text>
      </svg>
    </div>
  );
}

function Hero() {
  const [typed, setTyped] = useState("");
  const line = "> initialising student_forum... chandigarh_university";
  useEffect(() => {
    if (reducedMotion()) {
      setTyped(line);
      return;
    }
    let i = 0;
    const timer = window.setInterval(() => {
      i += 1;
      setTyped(line.slice(0, i));
      if (i >= line.length) window.clearInterval(timer);
    }, 30);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <section id="top" className="relative isolate flex min-h-screen items-center overflow-hidden">
      <div className="home-grid" aria-hidden="true" />
      <div className="relative mx-auto grid w-full max-w-7xl items-center gap-8 px-4 pt-28 pb-24 sm:px-6 lg:grid-cols-[1.15fr_1fr]">
        <div>
          <p className="home-mono min-h-10 text-xs text-cyan-300 sm:min-h-0 sm:text-sm">{typed}<span className="home-caret" aria-hidden="true">█</span></p>
          <h1 className="home-heading mt-5 text-[clamp(3.6rem,10vw,7.5rem)] leading-[0.95] font-bold text-white">
            <span className="home-glitch block" data-text="RISE."><Scramble text="RISE." delay={300} /></span>
            <span className="home-glitch block" data-text="LEARN."><Scramble text="LEARN." delay={550} /></span>
            <span className="home-gold block"><Scramble text="LEAD." delay={850} /></span>
          </h1>
          <p className="home-rise mt-7 max-w-xl text-lg text-slate-300" style={{ animationDelay: "1100ms" }}>
            We are the IETE Student Forum at Chandigarh University: students who build, organise and lead,
            part of a professional society serving India since 1953.
          </p>
          <div className="home-rise mt-8 flex flex-wrap gap-4" style={{ animationDelay: "1300ms" }}>
            <a href={JOIN_URL} target="_blank" rel="noopener noreferrer" className="home-button rounded-xl px-7 py-3.5 font-semibold text-slate-950">Join now</a>
            <a href="#events" className="home-button-outline rounded-xl px-7 py-3.5 font-semibold text-cyan-100">See our events</a>
          </div>
          <p className="home-rise mt-8 text-lg text-amber-200/80" lang="sa" style={{ animationDelay: "1500ms" }}>सह वीर्यं करवावहै</p>
        </div>
        <Reactor className="w-64 sm:w-80 lg:w-full" />
      </div>
      <a href="#about" className="home-scrollcue absolute bottom-6 left-1/2 -translate-x-1/2 text-cyan-300" aria-label="Scroll down">
        <Icon d="M6 9l6 6 6-6" className="size-8" />
      </a>
    </section>
  );
}

function Marquee() {
  const row = [...TEAMS, ...TEAMS];
  return (
    <div className="relative z-10 -my-3 -rotate-1 overflow-hidden border-y border-cyan-400/30 bg-[#0a1024]/90 py-4 shadow-[0_0_40px_rgba(56,189,248,.18)] backdrop-blur" aria-label="Our teams">
      <div className="home-marquee flex w-max items-center gap-6">
        {row.map((team, i) => (
          <span key={i} aria-hidden={i >= TEAMS.length} className="home-mono flex items-center gap-6 whitespace-nowrap text-sm font-medium tracking-widest text-cyan-100 uppercase">
            {team}<span className="text-amber-300">▲</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function Terminal() {
  const [ref, seen] = useInView<HTMLDivElement>(0.3);
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!seen) return;
    if (reducedMotion()) {
      setCount(TERMINAL.length);
      return;
    }
    const timer = window.setInterval(() => {
      setCount((c) => {
        if (c + 1 >= TERMINAL.length) window.clearInterval(timer);
        return c + 1;
      });
    }, 420);
    return () => window.clearInterval(timer);
  }, [seen]);
  return (
    <div ref={ref} className="home-glass overflow-hidden rounded-2xl">
      <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
        <span className="size-3 rounded-full bg-red-400" /><span className="size-3 rounded-full bg-amber-300" /><span className="size-3 rounded-full bg-emerald-400" />
        <span className="home-mono ml-2 text-xs text-slate-400">iete@cu:~</span>
      </div>
      <div className="home-mono min-h-72 space-y-1.5 p-5 text-sm">
        {TERMINAL.slice(0, count).map((text) => (
          <p key={text} className={cx("home-line", text.startsWith("$") ? "text-emerald-300" : "text-slate-200")}>{text}</p>
        ))}
        {count < TERMINAL.length || <span className="home-caret text-emerald-300" aria-hidden="true">█</span>}
      </div>
    </div>
  );
}

function About() {
  return (
    <section id="about" className="scroll-mt-20 px-4 py-28 sm:px-6">
      <div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="what_is_iete" title="A national society, right here on campus" />
        <div className="grid items-start gap-8 lg:grid-cols-2">
          <Reveal from="left"><Terminal /></Reveal>
          <div className="grid grid-cols-2 gap-4">
            {STATS.map((s, i) => (
              <Reveal key={s.label} from="zoom" delay={i * 120} className="h-full">
                <Tilt className="h-full">
                  <div className="home-glass h-full rounded-2xl p-6">
                    <div className="home-heading home-glow text-3xl font-bold text-white sm:text-5xl"><CountUp value={s.value} suffix={s.suffix} decimals={s.decimals} plain={s.plain} /></div>
                    <div className="mt-3 text-sm text-slate-300">{s.label}</div>
                  </div>
                </Tilt>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function WhyJoin() {
  return (
    <section id="why" className="scroll-mt-20 px-4 py-28 sm:px-6">
      <div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="why_join" title="More than a line on your resume" text="Create. Collaborate. Conquer. Here is what being part of the forum gives you." />
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {BENEFITS.map((b, i) => (
            <Reveal key={b.title} from="zoom" delay={(i % 3) * 120} className="h-full">
              <Tilt className="h-full">
                <div className="home-glass group h-full rounded-2xl p-7">
                  <span className="home-icon inline-flex size-14 items-center justify-center rounded-xl text-cyan-200"><Icon d={b.icon} className="size-7" /></span>
                  <h3 className="home-heading mt-5 text-xl font-semibold text-white">{b.title}</h3>
                  <p className="mt-2 text-sm text-slate-300">{b.text}</p>
                </div>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function Events() {
  const track = useRef<HTMLDivElement>(null);
  const fill = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onScroll = () => {
      if (!track.current || !fill.current) return;
      const box = track.current.getBoundingClientRect();
      const progress = Math.max(0, Math.min(1, (window.innerHeight * 0.6 - box.top) / box.height));
      fill.current.style.transform = `scaleY(${progress})`;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return (
    <section id="events" className="scroll-mt-20 px-4 py-28 sm:px-6">
      <div className="mx-auto max-w-6xl">
        <SectionTitle eyebrow="event_log" title="What we've done so far" text="From our first day to a stage shared with students from across India." />
        <div ref={track} className="relative">
          <div className="absolute top-0 bottom-0 left-4 w-0.5 bg-white/10 md:left-1/2" aria-hidden="true">
            <div ref={fill} className="home-timeline size-full origin-top scale-y-0" />
          </div>
          <ol className="space-y-14">
            {EVENTS.map((e, i) => {
              const flip = i % 2 === 1;
              return (
                <li key={e.name} className="relative pl-12 md:grid md:grid-cols-2 md:gap-14 md:pl-0">
                  <span className="home-node absolute top-8 left-4 size-4 -translate-x-1/2 rounded-full md:left-1/2" aria-hidden="true" />
                  <Reveal from={flip ? "right" : "left"} className={cx(flip && "md:col-start-2")}>
                    <Tilt>
                      <article className="home-glass group overflow-hidden rounded-2xl">
                        <div className="home-photo relative overflow-hidden">
                          <img src={e.photo} alt={e.alt} loading="lazy" className="aspect-video w-full object-cover transition duration-700 group-hover:scale-110" />
                          <span className="home-mono absolute top-3 left-3 rounded bg-black/70 px-2 py-1 text-xs tracking-widest text-amber-300">{e.tag}</span>
                        </div>
                        <div className="p-6">
                          <p className="home-mono text-xs text-cyan-300">{e.when}</p>
                          <h3 className="home-heading mt-2 text-2xl font-bold text-white">{e.name}</h3>
                          <p className="mt-3 text-sm text-slate-300">{e.text}</p>
                          <ul className="mt-4 flex flex-wrap gap-2">
                            {e.points.map((p) => <li key={p} className="rounded-md border border-cyan-400/30 bg-cyan-400/10 px-2.5 py-1 text-xs font-medium text-cyan-100">{p}</li>)}
                          </ul>
                        </div>
                      </article>
                    </Tilt>
                  </Reveal>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </section>
  );
}

function Faculty() {
  return (
    <section id="faculty" className="scroll-mt-20 px-4 py-28 sm:px-6">
      <div className="mx-auto max-w-7xl">
        <SectionTitle eyebrow="our_mentors" title="The faculty behind us" text="The people who guide the forum and make everything we do possible." />
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {FACULTY.map((f, i) => (
            <li key={f.name}>
              <Reveal from="zoom" delay={(i % 4) * 110} className="h-full">
                <Tilt className="h-full">
                  <a href={f.url} target="_blank" rel="noopener noreferrer" aria-label={`${f.name}, ${f.role}, on LinkedIn`}
                     className="home-glass group flex h-full flex-col items-center rounded-2xl p-6 text-center">
                    <span className="home-avatar relative flex size-32 items-center justify-center rounded-full">
                      <span className="home-heading relative flex size-[7.5rem] items-center justify-center overflow-hidden rounded-full bg-[#0a1024] text-3xl font-bold text-white">
                        {f.photo ? <img src={f.photo} alt="" loading="lazy" className="size-full object-cover" /> : initials(f.name)}
                      </span>
                    </span>
                    <span className="home-heading mt-5 text-lg font-semibold text-white">{f.name}</span>
                    <span className="mt-1 text-sm text-slate-300">{f.role}</span>
                    <span className="home-mono mt-auto pt-4 text-xs text-amber-300 transition group-hover:tracking-widest">linkedin →</span>
                  </a>
                </Tilt>
              </Reveal>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Contact() {
  const ways = [
    { label: "Email", value: CONTACT.email, href: `mailto:${CONTACT.email}`, icon: "M3 7l9 6 9-6M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1" },
    { label: "Phone", value: CONTACT.phone, href: CONTACT.phoneHref, icon: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A15 15 0 0 1 3 6a2 2 0 0 1 2-2" },
    { label: "Instagram", value: CONTACT.instagramHandle, href: CONTACT.instagram, icon: "M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4m5 5a4 4 0 1 0 0 8 4 4 0 0 0 0-8m5-1.5h.01" },
    { label: "LinkedIn", value: "IETE Student Forum, CU", href: CONTACT.linkedin, icon: "M8 10v7M8 7v.01M12 17v-7m0 3a3 3 0 0 1 6 0v4M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2" },
  ];
  return (
    <section id="contact" className="scroll-mt-20 px-4 py-28 sm:px-6">
      <div className="mx-auto max-w-5xl">
        <SectionTitle eyebrow="get_in_touch" title="Be part of something extraordinary" text="Want to join, partner with us or ask a question? Message us, and follow our Instagram to hear about the next recruitment drive." />
        <div className="grid gap-5 sm:grid-cols-2">
          {ways.map((w, i) => (
            <Reveal key={w.label} from="zoom" delay={i * 100}>
              <Tilt>
                <a href={w.href} {...(w.href.startsWith("http") ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                   className="home-glass group flex items-center gap-4 rounded-2xl p-6">
                  <span className="home-icon inline-flex size-14 shrink-0 items-center justify-center rounded-xl text-cyan-200"><Icon d={w.icon} className="size-7" /></span>
                  <span className="min-w-0">
                    <span className="home-mono block text-xs tracking-widest text-cyan-300 uppercase">{w.label}</span>
                    <span className="block truncate text-lg font-semibold text-white">{w.value}</span>
                  </span>
                </a>
              </Tilt>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/10 bg-[#060914]/80 px-4 py-10 text-sm text-slate-400 sm:px-6">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
        <p>© {new Date().getFullYear()} IETE Student Forum · Chandigarh University</p>
        <p className="home-mono text-cyan-200">create · collaborate · conquer</p>
        <Link to="/login" className="font-semibold text-amber-300 hover:underline">Team portal login →</Link>
      </div>
    </footer>
  );
}

export function HomePage() {
  useEffect(() => {
    document.documentElement.classList.add("home-smooth");
    return () => document.documentElement.classList.remove("home-smooth");
  }, []);
  return (
    <div className="home-page relative isolate overflow-x-clip">
      <ParticleField />
      <div className="home-spotlight" aria-hidden="true" />
      <Header />
      <main>
        <Hero />
        <Marquee />
        <About />
        <WhyJoin />
        <Events />
        <Faculty />
        <Contact />
      </main>
      <Footer />
    </div>
  );
}
