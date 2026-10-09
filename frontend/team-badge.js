// The badge shown before each driver's code on the leaderboard.
// `match` is tested against the team name from the API, so one entry can also
// cover a team's older names. Teams with a `logo` show the image; the rest show
// `abbr` on a `color` background (`dark: true` = dark text, for light colors).
const TEAM_BADGES = [
  { match: /red bull/i, abbr: "RBR", color: "#3671C6", logo: "assets/team-logos/redbull.png" },
  { match: /ferrari/i, abbr: "FER", color: "#E8002D", logo: "assets/team-logos/ferrari.png" },
  { match: /mercedes/i, abbr: "MER", color: "#27F4D2", dark: true, logo: "assets/team-logos/mercedes.png" },
  { match: /mclaren/i, abbr: "MCL", color: "#FF8000", logo: "assets/team-logos/mclaren.png" },
  { match: /aston martin/i, abbr: "AM", color: "#229971", logo: "assets/team-logos/astonmartin.png" },
  { match: /alpine/i, abbr: "ALP", color: "#FF87BC", dark: true, logo: "assets/team-logos/alpine.png" },
  { match: /williams/i, abbr: "WIL", color: "#64C4FF", dark: true, logo: "assets/team-logos/williams.png" },
  { match: /racing bulls|alphatauri|visa cash app|^rb$/i, abbr: "RB", color: "#6692FF", dark: true, logo: "assets/team-logos/racingbull.png" },
  { match: /sauber|alfa romeo/i, abbr: "SAU", color: "#52E252", dark: true },
  { match: /haas/i, abbr: "HAS", color: "#B6BABD", dark: true, logo: "assets/team-logos/haas.png" },
  { match: /audi/i, abbr: "AUD", color: "#B3202D", logo: "assets/team-logos/audi.png" },
  { match: /cadillac/i, abbr: "CAD", color: "#00563F", logo: "assets/team-logos/cadillac.png" },
];

function teamBadgeHTML(team) {
  if (!team) return "";
  const entry = TEAM_BADGES.find((t) => t.match.test(team));
  if (!entry) return "";
  if (entry.logo) {
    return `<img class="team-badge team-badge-logo" src="${entry.logo}" alt="${entry.abbr}" title="${team}">`;
  }
  const textColor = entry.dark ? "#111" : "#fff";
  return `<span class="team-badge" style="background:${entry.color};color:${textColor}" title="${team}">${entry.abbr}</span>`;
}
