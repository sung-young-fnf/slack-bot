module.exports = {
  apps: [{
    name: 'slack-briefing-bot',
    script: 'src/main.py',
    interpreter: 'python',
    interpreter_args: '',
    cwd: 'C:/Users/AC0833/project/slack_bot',
    watch: false,
    restart_delay: 3000,
    max_restarts: 10,
    env: {
      PATH: 'C:/Users/AC0833/project/slack_bot/venv/Scripts;' + process.env.PATH,
    }
  }]
}
