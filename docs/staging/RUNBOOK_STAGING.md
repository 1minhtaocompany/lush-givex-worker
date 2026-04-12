# Staging Runbook — Phase 4

## Start Staging

```bash
# 1. Verify environment
python -m unittest discover tests  # all pass

# 2. Start 1 worker (warm-up)
python main.py --workers 1 --mode staging

# 3. Monitor metrics (5 phút đầu)
# Check logs: tail -f logs/staging.log

# 4. Scale to 3 workers after 30 min stable
python main.py --workers 3 --mode staging
```

## Kill-Switch (Emergency Stop)

```bash
python main.py --stop-all
# OR: Ctrl+C → graceful shutdown
# OR: kill -SIGTERM $(pgrep -f "main.py")
```

## Check Metrics

```bash
python -c "from integration.runtime import Runtime; r = Runtime(); print(r.get_deployment_status())"
```

## Rollback

Automatic rollback triggers:
- error_rate > 5% → auto scale down
- restarts > 3/hr → auto scale down
- memory > 1.5GB → manual intervention needed

## Log Format

```
timestamp | worker_id | trace_id | state | action | status
```
