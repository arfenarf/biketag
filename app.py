from flask import Flask, render_template, request, url_for
from maps import load_and_build_map, build_map
from flask_wtf import FlaskForm
from wtforms import SelectMultipleField, SubmitField
from flask_sqlalchemy import SQLAlchemy
import os
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

SECRET_KEY = os.urandom(32)


class PersonForm(FlaskForm):
    prefix = "person"
    options = SelectMultipleField("Select person(s)")
    peoplesubmit = SubmitField("Submit")


app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

from sqlalchemy import Integer, String, Float
from sqlalchemy.orm import Mapped, mapped_column


class Person(db.Model):
    person_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    cluster: Mapped[int] = mapped_column(Integer, nullable=True)
    convex_hull_area: Mapped[float] = mapped_column(Float, nullable=True)
    location_density: Mapped[float] = mapped_column(Float, nullable=True)
    location_count: Mapped[int] = mapped_column(Integer)


with app.app_context():
    db.create_all()
    db.session.commit()
    m, map_df, person_df, gdf = load_and_build_map(
        "data/biketag.tsv", "data/person_nodes.csv"
    )
    print(person_df.columns)
    print(person_df.head())
    for person, row in person_df.iterrows():
        p = Person(
            person_id=row.person_id,
            person=person,
            cluster=row.cluster,
            convex_hull_area=round(row.convex_hull_area, 2),
            location_density=round(row.location_density, 4),
            location_count=row.location_count,
        )
        db.session.add(p)
    db.session.commit()


@app.route("/", methods=["GET", "POST"])
def index():
    sort = request.args.get("sort", "person_id")
    reverse = request.args.get("direction", "asc") == "desc"
    m, map_df, person_df, gdf = load_and_build_map(
        "data/biketag.tsv", "data/person_nodes.csv"
    )

    peopleform = PersonForm()
    people = Person.query
    selector_options = [(person.person, person.person) for person in people if person.location_count > 2]
    # people = [(person, person) for person in map_df.person.unique()]
    selector_options.sort()
    peopleform.options.choices = selector_options

    if peopleform.validate_on_submit() and peopleform.peoplesubmit.data:
        print(peopleform.options.data)
        m = build_map(
            map_df.loc[map_df.person.isin(peopleform.options.data)], person_df, gdf
        )

    # set the iframe width and height
    m.get_root().width = "800px"
    m.get_root().height = "600px"
    iframe = m.get_root()._repr_html_()

    return render_template(
        "iframe.html",
        title="Bike Tag Map!",
        iframe=iframe,
        peopleform=peopleform,
        peopletable=people
    )


@app.route("/item/<int:id>")
def flask_link(id):
    element = get_element_by_id(id)
    return "<h1>{}</h1><p>{}</p><hr><small>id: {}</small>".format(
        element.name, element.description, element.id
    )


if __name__ == "__main__":
    app.run(debug=True)
