/** The slate's date in ET, rolled over at 6am (scripts/fetch-tonight.mjs). */
export const slateDate = (now = new Date()) =>
  new Date(now.getTime() - 6 * 3600e3).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
