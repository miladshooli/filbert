#!/bin/sh
# نام/ایمیل نویسنده و committer همه کامیت‌ها را یکدست می‌کند و main را force-push می‌کند.
# اجرا از ریشه مخزن:  sh tools/rewrite_authors.sh
set -e
NEW_NAME="${NEW_NAME:-Milad Shooli}"
NEW_EMAIL="${NEW_EMAIL:-49821092+miladshooli@users.noreply.github.com}"
export NEW_NAME NEW_EMAIL
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --env-filter '
export GIT_AUTHOR_NAME="$NEW_NAME" GIT_AUTHOR_EMAIL="$NEW_EMAIL"
export GIT_COMMITTER_NAME="$NEW_NAME" GIT_COMMITTER_EMAIL="$NEW_EMAIL"
' -- --all
git log --format='%an <%ae>' | sort | uniq -c
git push --force-with-lease origin main
echo "done"
