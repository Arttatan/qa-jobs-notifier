export const CV_FILE_NAME = "Tatanov Artem QA engineer.pdf";

export const candidateProfile = {
  name: "Artem Tatanov",
  location: "Lisbon, Portugal",
  email: "art.tatan@gmail.com",
  phone: "+351 913 95 7670",
  linkedin: "https://www.linkedin.com/in/artem-tatanov-138505256/",
  headline: "QA Engineer",
  years: "QA since July 2021",
  skills: [
    "Manual testing for web, mobile, and API",
    "Playwright, JavaScript, Python, CI/CD",
    "Postman, Charles Proxy, SQL",
    "Jira, YouTrack, TestRail, Confluence, Slack",
    "BrowserStack, Android, iOS",
  ],
  roles: [
    {
      company: "White Rainbow Dental clinic",
      title: "QA Engineer",
      when: "Oct 2023–present",
      remote: true,
      facts: [
        "Owns API and UI coverage for a patient and staff product.",
        "Worked with developers on a React migration.",
        "Updated more than 100 test cases after an architecture change.",
        "Set up CI/CD for tests and deployment.",
        "Checked SQL data during a migration.",
        "Post-release bugs stayed at zero for 3 product cycles.",
      ],
    },
    {
      company: "For you (Beauty APP)",
      title: "QA Engineer",
      when: "Nov 2022–Sep 2023",
      remote: true,
      facts: [
        "Tested iOS and Android builds for a beauty startup.",
        "Wrote the first test cases and tracked bugs in Jira and ClickUp.",
        "Checked analytics events in GA and GTM.",
        "Customer satisfaction scores improved by 20% with QA input on high-priority bugs.",
      ],
    },
    {
      company: "Conversion Advocates",
      title: "QA Engineer",
      when: "Jul 2021–Nov 2022",
      remote: true,
      facts: [
        "Tested landing pages, funnels, and ecommerce flows, including A/B variants.",
        "Customer-reported bugs fell by 5% and internal defects by 3%.",
      ],
    },
  ],
  education: [
    "St. Petersburg Mining University, Engineer",
    "QA Tester course, 2021",
    "ProductStar test automation, 2022–2023",
    "Netology HTML and CSS, 2021",
  ],
  limits: [
    "He has not held a Project Manager title.",
    "Do not invent employers, dates, tools, or metrics.",
    "Do not describe him as an ML engineer or AI engineer.",
  ],
} as const;
