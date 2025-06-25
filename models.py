from flask import Flask

app = Flask(__name__)

with app.app_context():
  def setup():
      print("Before first request hook works!")

@app.route('/')
def hello():
    return "Hello!"

if __name__ == '__main__':
    app.run()
