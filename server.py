from flask import Flask, render_template, request, session, url_for, redirect, jsonify
import pymysql.cursors
from flask_hashing import Hashing

app = Flask(__name__)
hashing = Hashing(app)
dbconn = pymysql.connect(
    host="localhost",
    port=3306,
    user="root",
    password="dankmemes",
    db="pricosha",
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor
)

@app.route('/', methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        data = request.get_json(force=True)
        # get the hashed password
        hashed_pass = hashing.hash_value(data['password'])

        query = 'SELECT * FROM person WHERE email = %s and password = %s'
        cursor = dbconn.cursor()
        cursor.execute(query, [data['email'], hashed_pass])
        result = cursor.fetchone()
        cursor.close()
        if (result):
            session['email'] = data['email']
            print("Succesful login on email", session['email'])
            return jsonify(redirect="home")
        else:
            error = True
            return render_template("login_page.html", error=error)
    else:
        return render_template("login_page.html")

@app.route('/home/', methods=["GET", "POST"])
def home():
    if request.method == "GET":
        # get content items visible to user
        query = 'SELECT * FROM contentitem NATURAL LEFT OUTER JOIN share ' \
                + 'WHERE fg_name IN (SELECT fg_name FROM person NATURAL JOIN belong WHERE email=%s) ' \
                + 'OR is_pub=1 ORDER BY post_time'
        cursor = dbconn.cursor()
        cursor.execute(query, session['email'])
        contentitems = cursor.fetchall()
        contentitems.reverse()

        # get all tags
        query2 = 'SELECT DISTINCT fname, lname, item_id, status, email_tagged FROM contentitem NATURAL JOIN (tag JOIN person ON tag.email_tagged=person.email)'
        cursor.execute(query2)
        tags = cursor.fetchall()

        # get all ratings
        query3 = 'SELECT * FROM contentitem NATURAL JOIN rate'
        cursor.execute(query3)
        ratings = cursor.fetchall()

        cursor.close()
        return render_template("home.html", email=session['email'], contentitems=contentitems, tags=tags, ratings=ratings)

    # related to accepting, declining, or adding tags    
    elif request.method == "POST":
        data = request.get_json(force=True)
        cursor = dbconn.cursor()
        if data['type'] == "TAG":
            if data['action'] == "ACCEPT":
                stmt = "UPDATE tag SET status=true WHERE item_id=%s AND email_tagged=%s"
                cursor.execute(stmt, [data['item_id'], session['email']])
                dbconn.commit()
                return jsonify(action="alert")
            elif data['action'] == "DECLINE":
                stmt = "DELETE FROM tag WHERE item_id=%s AND email_tagged=%s"
                cursor.execute(stmt, [data['item_id'], session['email']])
                dbconn.commit()
                return jsonify(action="alert")
            elif data['action'] == "ADD":
                # check first to see if the tagged person can see the content item
                query = "SELECT * FROM belong WHERE email=%s AND owner_email=%s AND fg_name=%s"
                cursor.execute(query, [data['email_tagged'], data['owner_email'], data['fg_name']])
                result = cursor.fetchone()
                if not result:
                    return jsonify(redirect="not visible")
                
                # check is a tag for that person already exists
                query = "SELECT * FROM tag WHERE email_tagged=%s AND item_id=%s"
                cursor.execute(query, [data['email_tagged'], data['item_id']])
                result = cursor.fetchone()
                if result:
                    return jsonify(redirect="exists")
                else:
                    stmt = "INSERT INTO tag VALUES (%s, %s, %s, %s, NOW())"
                    status = False
                    if data['email_tagged'] == session['email']:
                        status = True
                    cursor.execute(stmt, [data['email_tagged'], session['email'], data['item_id'], status])
                    dbconn.commit()
                    return jsonify(redirect="success")
        cursor.close()

@app.route('/post_content/', methods=["GET","POST"])
def post_content():
    if request.method == "GET":
        query = 'SELECT * FROM person NATURAL JOIN belong WHERE email = %s'
        cursor = dbconn.cursor()
        cursor.execute(query, [session['email']])
        friend_groups = cursor.fetchall()
        cursor.close()
        return render_template("post_content.html", friend_groups=friend_groups)
    elif request.method == "POST":
        data = request.get_json(force=True)
        cursor = dbconn.cursor()

        # first create the content item
        stmt_contentitem = 'INSERT INTO contentitem VALUES (NULL, %s, NOW(), %s, %s, %s)'
        cursor.execute(stmt_contentitem, [session['email'], data['file_path'], data['item_name'], data['is_pub']])

        # then share it to those groups
        query = 'SELECT max(item_id) FROM contentitem'
        cursor.execute(query)
        item_id = cursor.fetchone()['max(item_id)']
        for pair in data['fg_pairs']:
            owner_email = pair.split(",")[1]
            fg_name = pair.split(",")[0]
            stmt_share = 'INSERT INTO share VALUES (%s, %s, %s)'
            cursor.execute(stmt_share, [owner_email, fg_name, item_id])
        cursor.close()
        dbconn.commit()

        print("successful post of", data)
        return jsonify(redirect="home")

@app.route('/add_friend/', methods=["GET","POST"])
def add_friend():
    if request.method == "GET":
        query = 'SELECT distinct fg_name FROM person NATURAL JOIN belong WHERE owner_email = %s'
        cursor = dbconn.cursor()
        cursor.execute(query, [session['email']])
        friend_groups = cursor.fetchall()
        cursor.close()
        return render_template("add_friend.html", friend_groups=friend_groups)
    elif request.method == "POST":
        data = request.get_json(force=True)
        cursor = dbconn.cursor()
        email = ''

        # if user put in email, just use that
        if len(data['email']) > 0:
            email = data['email']

        # if we only have name, find email based on name
        # if there's duplicates, ask used to enter email
        else:
            query = 'SELECT email FROM person WHERE fname=%s AND lname=%s'
            cursor.execute(query, [data['fname'], data['lname']])
            result = cursor.fetchall()

            if len(result) == 0:
                return jsonify(redirect="none")
            elif len(result) > 1:
                return jsonify(redirect="duplicate")
            elif len(result) == 1:
                email = result[0]['email']

        # once we have email, check if person is already in group
        query = 'SELECT email FROM belong WHERE email=%s AND owner_email=%s AND fg_name=%s'
        cursor.execute(query, [email, session['email'], data['fg_name']])
        result = cursor.fetchone()
        if (result):
            return jsonify(redirect="exists")
        else:
            stmt = 'INSERT INTO belong VALUES (%s, %s, %s)'
            cursor.execute(stmt, [email, session['email'], data['fg_name']])
            cursor.close()
            dbconn.commit()
            return jsonify(redirect="success")


        
app.secret_key = 'some key that you will never guess'
#Run the app on localhost port 5000
#debug = True -> you don't have to restart flask
#for changes to go through, TURN OFF FOR PRODUCTION
if __name__ == "__main__":
    app.run('127.0.0.1', 5000, debug = True)
