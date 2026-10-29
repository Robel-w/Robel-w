"""Updates dark_mode.svg with live GitHub stats and a running age ("uptime").

Env vars (set by the GitHub Action):
  ACCESS_TOKEN  personal access token (classic) with `read:user` (+ `repo` to count private commits)
  USER_NAME     GitHub username
"""
import datetime
import os
import re
import sys

import requests
from dateutil import relativedelta

BIRTHDAY = datetime.datetime(2004, 12, 17)
SVG_FILE = "dark_mode.svg"
LINE_WIDTH = 56  # must match N in the card generator

API = "https://api.github.com/graphql"


def gql(query, variables, token):
    r = requests.post(
        API,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def age_string(today=None):
    today = today or datetime.datetime.today()
    d = relativedelta.relativedelta(today, BIRTHDAY)

    def unit(n, word):
        return f"{n} {word}{'s' if n != 1 else ''}"

    s = f"{unit(d.years, 'year')}, {unit(d.months, 'month')}, {unit(d.days, 'day')}"
    if d.months == 0 and d.days == 0:
        s += " 🎂"
    return s


def fetch_stats(user, token):
    q = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        repositories(ownerAffiliations: OWNER, first: 100, after: $cursor) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes { stargazerCount }
        }
        repositoriesContributedTo(first: 1,
          contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
      }
    }"""
    stars, cursor = 0, None
    while True:
        u = gql(q, {"login": user, "cursor": cursor}, token)["user"]
        stars += sum(n["stargazerCount"] for n in u["repositories"]["nodes"])
        if not u["repositories"]["pageInfo"]["hasNextPage"]:
            break
        cursor = u["repositories"]["pageInfo"]["endCursor"]

    created = datetime.datetime.strptime(u["createdAt"], "%Y-%m-%dT%H:%M:%SZ")
    commits = 0
    cq = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          restrictedContributionsCount
        }
      }
    }"""
    now = datetime.datetime.utcnow()
    for year in range(created.year, now.year + 1):
        start = max(created, datetime.datetime(year, 1, 1))
        end = min(now, datetime.datetime(year, 12, 31, 23, 59, 59))
        c = gql(
            cq,
            {
                "login": user,
                "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            token,
        )["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]

    return {
        "repos": u["repositories"]["totalCount"],
        "contrib": u["repositoriesContributedTo"]["totalCount"],
        "stars": stars,
        "followers": u["followers"]["totalCount"],
        "commits": commits,
    }


def set_tspan(svg, tspan_id, content):
    pattern = re.compile(r'(<tspan[^>]*id="%s"[^>]*>)(.*?)(</tspan>)' % re.escape(tspan_id), re.S)
    if not pattern.search(svg):
        raise KeyError(f"tspan id not found in SVG: {tspan_id}")
    return pattern.sub(lambda m: m.group(1) + content + m.group(3), svg, count=1)


def justify(svg, key, data_id, dots_id, value, extra_len=0):
    """Rewrite a value and resize the dotted filler so the line keeps its width."""
    value = str(value)
    value_len = len(value) + extra_len
    just = max(2, LINE_WIDTH - len(key) - 1 - value_len - 2)
    svg = set_tspan(svg, data_id, value)
    return set_tspan(svg, dots_id, " " + "." * just + " ")


def commas(n):
    return f"{n:,}"


def main():
    user = os.environ.get("USER_NAME", "robel-w")
    token = os.environ.get("ACCESS_TOKEN")
    svg = open(SVG_FILE, encoding="utf-8").read()

    age = age_string()
    svg = justify(svg, "Uptime", "age_data", "age_dots", age)

    if token:
        s = fetch_stats(user, token)
    else:
        print("ACCESS_TOKEN not set - only updating age.", file=sys.stderr)
        s = None

    if s:
        repo_val = commas(s["repos"])
        extra = len(" {Contributed: ") + len(commas(s["contrib"])) + 1
        svg = justify(svg, "Repos", "repo_data", "repo_dots", repo_val, extra_len=extra)
        svg = set_tspan(svg, "contrib_data", commas(s["contrib"]))
        svg = justify(svg, "Commits", "commit_data", "commit_dots", commas(s["commits"]))
        svg = justify(svg, "Stars", "star_data", "star_dots", commas(s["stars"]))
        svg = justify(svg, "Followers", "follower_data", "follower_dots", commas(s["followers"]))
        print("Stats:", s)

    open(SVG_FILE, "w", encoding="utf-8").write(svg)
    print("Updated", SVG_FILE, "| uptime:", age)


if __name__ == "__main__":
    main()
