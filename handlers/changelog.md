# Changelog

## Current State (Stable ✅)
- Bot starts and responds to /start
- Persistent reply keyboard (bottom buttons) working
- Inline nav buttons working
- Task list renders with live ✅/❌ status
- Channel join verification via get_chat_member()
- Daily bonus claim working
- Earnings screen with balance, rank, leaderboard
- Share & Refer screens with invite link
- Withdrawal flow (under development notice)
- Admin panel: manage tasks, view withdrawals, broadcast, stats
- PostgreSQL via Railway addon
- Error handler silences "Message not modified" noise

## Known Broken (needs fix)
- Reply keyboard buttons (Tasks, Earnings, Share, Refer) require
  an extra tap — open a bridge message instead of direct content
- Bot not admin in channel → task verification silently fails

## Features Not Yet Built
- Configurable reward amounts from admin panel
- Top 10 earners in admin stats
- Real withdrawal processing (currently shows "under development")
- Weekly leaderboard reset
- Ban/unban user from admin panel