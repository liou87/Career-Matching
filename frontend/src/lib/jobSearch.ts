export type JobSite = "lagou" | "zhipin" | "51job";

export const JOB_SITES: { value: JobSite; label: string }[] = [
  { value: "lagou", label: "拉勾网" },
  { value: "zhipin", label: "Boss直聘" },
  { value: "51job", label: "前程无忧" },
];

// 拉勾网的 city 参数直接接受城市中文名，能精确按城市过滤。
// Boss直聘/前程无忧的城市筛选要用数字编码（没有现成的城市名转编码表），
// 这里把城市名拼进关键词里做软过滤，不保证精确，但不会出错。
export function buildJobSearchUrl(site: JobSite, role: string, city: string): string {
  if (site === "lagou") {
    const cityParam = encodeURIComponent(city || "全国");
    return `https://www.lagou.com/wn/jobs?kd=${encodeURIComponent(role)}&city=${cityParam}&fromSearch=true&pn=1`;
  }
  const keyword = encodeURIComponent(city ? `${role} ${city}` : role);
  if (site === "zhipin") {
    return `https://www.zhipin.com/web/geek/job?query=${keyword}&city=100010000`;
  }
  return `https://we.51job.com/pc/search?jobArea=000000&keyword=${keyword}`;
}
