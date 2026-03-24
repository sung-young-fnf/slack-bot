module.exports = {
  apps: [{
    name: 'slack-briefing-bot',
    script: 'src/main.py',
    interpreter: './venv/Scripts/python',
    watch: false,
    restart_delay: 3000,
  }]
}
