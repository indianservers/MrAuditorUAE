const star =
  "0,-5 1.5,-1.6 5,-1.5 2.3,1 3,4.5 0,2.5 -3,4.5 -2.3,1 -5,-1.5 -1.5,-1.6";
export function CountryFlag({ country }: { country: string }) {
  const jack = (
    <>
      <rect width="60" height="40" fill="#173567" />
      <path d="M0 0L60 40M60 0L0 40" stroke="white" strokeWidth="9" />
      <path d="M0 0L60 40M60 0L0 40" stroke="#c93243" strokeWidth="3" />
      <path d="M30 0V40M0 20H60" stroke="white" strokeWidth="13" />
      <path d="M30 0V40M0 20H60" stroke="#c93243" strokeWidth="7" />
    </>
  );
  const graphic =
    country === "IN" ? (
      <>
        <path fill="#ff9933" d="M0 0H60V13.34H0z" />
        <path fill="white" d="M0 13.33H60V26.67H0z" />
        <path fill="#138808" d="M0 26.66H60V40H0z" />
        <circle cx="30" cy="20" r="5" fill="none" stroke="#183a87" />
        {Array.from({ length: 24 }, (_, i) => (
          <path
            key={i}
            d="M30 20v-5"
            stroke="#183a87"
            strokeWidth=".35"
            transform={`rotate(${i * 15} 30 20)`}
          />
        ))}
      </>
    ) : country === "AE" ? (
      <>
        <path fill="#00732f" d="M0 0H60V13.34H0z" />
        <path fill="white" d="M0 13.33H60V26.67H0z" />
        <path fill="#151515" d="M0 26.66H60V40H0z" />
        <path fill="#ef3340" d="M0 0H15V40H0z" />
      </>
    ) : country === "GB" ? (
      jack
    ) : country === "US" ? (
      <>
        {Array.from({ length: 13 }, (_, i) => (
          <rect
            key={i}
            y={(i * 40) / 13}
            width="60"
            height={40 / 13 + 0.1}
            fill={i % 2 ? "white" : "#b22234"}
          />
        ))}
        <rect width="26" height="22" fill="#3c3b6e" />
        {Array.from({ length: 30 }, (_, i) => (
          <circle
            key={i}
            cx={3 + (i % 6) * 4}
            cy={3 + Math.floor(i / 6) * 4}
            r=".75"
            fill="white"
          />
        ))}
      </>
    ) : country === "SG" ? (
      <>
        <rect width="60" height="40" fill="white" />
        <rect width="60" height="20" fill="#ef3340" />
        <circle cx="12" cy="10" r="7" fill="white" />
        <circle cx="15" cy="10" r="6" fill="#ef3340" />
        {[0, 1, 2, 3, 4].map((i) => (
          <polygon
            key={i}
            points={star}
            fill="white"
            transform={`translate(${25 + Math.cos((i * Math.PI * 2) / 5) * 5} ${10 + Math.sin((i * Math.PI * 2) / 5) * 5}) scale(.35)`}
          />
        ))}
      </>
    ) : country === "SA" ? (
      <>
        <rect width="60" height="40" fill="#006c35" />
        <text x="30" y="20" textAnchor="middle" fill="white" fontSize="7">
          لا إله إلا الله محمد رسول الله
        </text>
        <path d="M14 29h31m-31-1v3" stroke="white" strokeWidth="1.5" />
      </>
    ) : country === "AU" ? (
      <>
        <rect width="60" height="40" fill="#173567" />
        <g transform="scale(.5)">{jack}</g>
        {[
          [16, 30],
          [45, 9],
          [39, 22],
          [52, 22],
          [45, 33],
        ].map(([x, y], i) => (
          <polygon
            key={i}
            points={star}
            fill="white"
            transform={`translate(${x} ${y}) scale(.65)`}
          />
        ))}
      </>
    ) : null;
  return graphic ? (
    <svg
      width="42"
      height="28"
      viewBox="0 0 60 40"
      role="img"
      aria-label={`${country} flag`}
      style={{ borderRadius: 3, border: "1px solid #dbe4ee" }}
    >
      {graphic}
    </svg>
  ) : (
    <span className="country-code">{country}</span>
  );
}
