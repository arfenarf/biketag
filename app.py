import os
from datetime import datetime

import pandas as pd
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from sqlalchemy import Integer, String, Float, DateTime
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column
from wtforms import SelectMultipleField, SubmitField

from maps import load_and_build_map, build_map
from plots import create_bokeh_network, create_plotly_distograms, create_plotly_heatmap


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class PersonForm(FlaskForm):
    prefix = "person"
    options = SelectMultipleField("Select person(s)")

    peoplesubmit = SubmitField("Update Map")


class Person(db.Model):
    person_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    cluster: Mapped[int] = mapped_column(Integer, nullable=True)
    convex_hull_area: Mapped[float] = mapped_column(Float, nullable=True)
    location_density: Mapped[float] = mapped_column(Float, nullable=True)
    location_count: Mapped[int] = mapped_column(Integer)

    def to_dict(self):
        return {field.name: getattr(self, field.name) for field in self.__table__.c}


class Tag(db.Model):
    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    placed_by: Mapped[str] = mapped_column(String, nullable=True)
    found_by: Mapped[str] = mapped_column(String, nullable=True)
    placed_by_id: Mapped[int] = mapped_column(Integer, nullable=True)
    found_by_id: Mapped[int] = mapped_column(Integer, nullable=True)
    placed_at_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    found_at_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    drive_distance_mi: Mapped[float] = mapped_column(Float, nullable=True)
    crow_distance_mi: Mapped[float] = mapped_column(Float, nullable=True)

    def to_dict(self):
        return {field.name: getattr(self, field.name) for field in self.__table__.c}


SECRET_KEY = os.urandom(32)

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


with app.app_context():
    db.create_all()
    db.session.commit()
    m, map_df, person_df, gdf = load_and_build_map("data/biketag.tsv")

    for person, row in person_df.iterrows():
        p = Person(
            person_id=row.person_id,
            person=person,
            cluster=row.cluster_label,
            convex_hull_area=round(row.convex_hull_area, 2),
            location_density=round(row.location_density, 4),
            location_count=row.location_count,
        )
        db.session.add(p)

    db.session.commit()

    for tag, row in gdf.iterrows():
        t = Tag(
            tag_id=row.tag_id,
            name=row["name"],
            placed_by=row.placed_by,
            found_by=row.found_by,
            placed_by_id=row.placed_by_id,
            found_by_id=row.found_by_id,
            placed_at_datetime=datetime.fromisoformat(row.placed_at_datetime),
            found_at_datetime=datetime.fromisoformat(row.found_at_datetime),
            drive_distance_mi=row.drive_distance_mi,
            crow_distance_mi=row.crow_dist_mi,
        )
        db.session.add(t)
    db.session.commit()

    print("this is just for debugging")


@app.route("/", methods=["GET", "POST"])
def index():
    m, map_df, person_df, gdf = load_and_build_map("data/biketag.tsv")

    peopleform = PersonForm()
    people = Person.query
    selector_options = [
        (person.person, person.person) for person in people if person.location_count > 2
    ]
    selector_options.sort()
    peopleform.options.choices = selector_options

    if peopleform.validate_on_submit() and peopleform.peoplesubmit.data:
        if not peopleform.options.data:
            peopleform.options.data = [
                person.person for person in people if person.location_count > 2
            ]
        m = build_map(map_df, person_df, gdf, peopleform=peopleform)

    # set the iframe width and height
    m.get_root().width = "800px"
    m.get_root().height = "600px"
    iframe = m.get_root()._repr_html_()

    return render_template(
        "map_table.html",
        title="Bike Tag Map!",
        iframe=iframe,
        peopleform=peopleform,
        peopletable=people,
    )


@app.route("/plots", methods=["GET"])
def show_plots():
    tags = Tag.query
    tag_df = pd.DataFrame([tag.to_dict() for tag in tags]).set_index("tag_id")

    # draw_network
    network_script, network_div = create_bokeh_network(person_df, tag_df)

    # time to find hist

    # distance hist
    distograms = create_plotly_distograms(tag_df)

    # frequency by month-year
    datemap = create_plotly_heatmap(tag_df)

    return render_template(
        "plots.html",
        title="Bike Tag Plots",
        script=network_script,
        div=network_div,
        distograms=distograms,
        datemap=datemap,
    )


if __name__ == "__main__":
    app.run(debug=True)
