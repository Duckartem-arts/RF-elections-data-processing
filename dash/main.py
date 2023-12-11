from dash import Dash, html, dash_table, dcc, callback, Output, Input
import plotly.express as px
import pandas as pd
import numpy as np
import json
import sqlite3
import plotly as plt
import zipfile
from urllib.request import urlopen

connection = sqlite3.connect("elections.db")

with open('russia.geojson', encoding='UTF-8') as response:
    counties = json.load(response)

app = Dash(__name__)

app.layout = html.Div([
    html.H1("Выборы в РФ"),
    html.Hr(),
    html.H2("Регионы"),
    html.Hr(),
    html.Div(children='Выберите регион'),
    dcc.Dropdown(pd.read_sql_query('SELECT region_name FROM region', connection)['region_name'],
                 'Вся Россия',
                 id='region_dropdown'),
    html.Div(children='Выберите год'),
    dcc.Dropdown(
        [2004, 2008, 2012, 2018],
        2012,
        id='year_dropdown'),
    html.Div(children='Отображать регионы по'),
    dcc.Dropdown(
        ['Явка'] + [f'Голоса за {cand}' for cand in
                    pd.read_sql_query('SELECT candidate_name FROM p_candidate', connection)['candidate_name']],
        'Явка',
        id='map_dropdown'),
    dcc.Graph(figure={}, id='map', style={'display': 'inline-block'}),
    html.Div(children=[
        dcc.Graph(figure={}, id='results', style={'display': 'inline-block'}),
        dcc.Graph(figure={}, id='turnout', style={'display': 'inline-block'})
    ]),
    html.H2("Межрегиональные показатели"),
    html.Hr(),
    dcc.Dropdown(
        [2004, 2008, 2012, 2018],
        2012,
        id='year_dropdown_2'),
    html.Div(children=[
        dcc.Graph(figure={}, id='turnout_best', style={'display': 'inline-block'}),
        dcc.Graph(figure={}, id='turnout_worst', style={'display': 'inline-block'})
    ]),
    html.H2("Показатели по кандидатам"),
    html.Hr(),
    dcc.Dropdown(
        pd.read_sql_query('SELECT candidate_name FROM p_candidate', connection)['candidate_name'],
        'Путин Владимир Владимирович',
        id='p_candidate_dropdown'),
    html.Div(children=[
        dcc.Graph(figure={}, id='perc_results', style={'display': 'inline-block'}),
        dcc.Graph(figure={}, id='abs_results', style={'display': 'inline-block'})
    ]),
    html.Div(children=[
        dcc.Graph(figure={}, id='cand_top5', style={'display': 'inline-block'}),
        dcc.Graph(figure={}, id='cand_worst5', style={'display': 'inline-block'})
    ]),
])


@callback(
    [Output('map', 'figure'),
     Output('region_dropdown', 'value')],
    [Input('map_dropdown', 'value'),
     Input('year_dropdown', 'value'),
     Input('map', 'clickData')]
)
def update_graph(param, year, clickData):
    connection = sqlite3.connect("elections.db")
    if clickData is None:
        region = 'Вся Россия'
    else:
        region = clickData['points'][0]['customdata'][0]
    if region == 'Вся Россия':
        if param == 'Явка':
            data = pd.read_sql_query(f"""
                SELECT region_id, region_name, ROUND(came * 1.0 / voters * 100, 2) AS turnout
                FROM 
                    president_elections_region 
                    INNER JOIN region USING(region_id)
                WHERE year = {year} AND region_id <> (
                    SELECT region_id
                    FROM region
                    WHERE region_name = 'Вся Россия'
                )
                """, connection)
            fig = px.choropleth(
                data,
                geojson=counties, locations='region_id', color='turnout', hover_data='region_name', height=500,
                width=1300)
        else:
            param = param[10:]
            data = pd.read_sql_query(f"""
                SELECT pec.region_id, region_name, ROUND(votes * 1.0 / voted * 100, 2) AS perc
                FROM 
                    president_elections_cand AS pec
                    INNER JOIN president_elections_region AS per ON pec.region_id = per.region_id AND pec.year = per.year
                    INNER JOIN region USING(region_id)
                WHERE pec.year = {year} AND pec.region_id <> (
                    SELECT region_id
                    FROM region
                    WHERE region_name = 'Вся Россия'
                ) AND candidate_id = (
                    SELECT candidate_id
                    FROM p_candidate
                    WHERE candidate_name = '{param}'
                )
                """, connection)
            fig = px.choropleth(
                data,
                geojson=counties, locations='region_id', color='perc', hover_data='region_name', height=500, width=1300)
    else:
        data = pd.read_sql_query(f"""
            SELECT region_id, region_name, CASE WHEN region_name = '{region}' THEN 'red' ELSE 'white' END AS color
            FROM region
            """, connection)
        fig = px.choropleth(
            data,
            geojson=counties, locations='region_id', color='color', hover_data='region_name', height=500, width=1300)
    fig.update_geos(
        lataxis_range=[40, 85], lonaxis_range=[18, 200]
    )
    return fig, region


@callback(
    [Output('results', 'figure'),
     Output('turnout', 'figure')],
    [Input('region_dropdown', 'value'),
     Input('year_dropdown', 'value')]
)
def update_graph(region, year):
    connection = sqlite3.connect("elections.db")
    data1 = pd.read_sql_query(f"""
    SELECT candidate_name, votes
    FROM 
        president_elections_cand
        INNER JOIN p_candidate USING(candidate_id)
    WHERE year = {year} AND region_id = (
        SELECT region_id
        FROM region
        WHERE region_name = '{region}'
        )
    """, connection)
    data2 = pd.read_sql_query(f"""
    SELECT voted, came - voted AS not_voted, voters - came AS not_came
    FROM president_elections_region
    WHERE year = {year} AND region_id = (
        SELECT region_id
        FROM region
        WHERE region_name = '{region}'
        )
    """, connection)
    fig1 = px.pie(data1, values='votes', names='candidate_name',
                  title=f'Итоги голосования')
    fig2 = px.pie(values=[data2['voted'][0], data2['not_voted'][0], data2['not_came'][0]],
                  names=['Проголосовали', 'Пришли, но не проголосовали', 'Не пришли'],
                  title=f'Явка')
    return fig1, fig2


@callback(
    [Output('turnout_best', 'figure'),
     Output('turnout_worst', 'figure')
     ],
    Input('year_dropdown_2', 'value')
)
def update_graph(year):
    connection = sqlite3.connect("elections.db")
    top5_turnout = pd.read_sql_query(f"""
    SELECT region_name, turnout, CASE WHEN region_name = 'Вся Россия' THEN 'r' ELSE 'b' END AS color
    FROM
        (
            SELECT *
            FROM
            (
                SELECT region_id, ROUND(came * 1.0 / voters * 100, 2) AS turnout
                FROM president_elections_region
                WHERE year = {year} AND region_id <> (
                SELECT region_id
                FROM region
                WHERE region_name = 'Вся Россия'
            )
                ORDER BY turnout DESC
                LIMIT 5
            ) best_ids
            UNION
            SELECT region_id, ROUND(came * 1.0 / voters * 100, 2) AS turnout
            FROM president_elections_region
            WHERE year = {year} AND region_id = (
                SELECT region_id
                FROM region
                WHERE region_name = 'Вся Россия'
            )
        ) AS region_ids
        INNER JOIN region USING(region_id)
        ORDER BY turnout DESC;
    """, connection)
    worst5_turnout = pd.read_sql_query(f"""
    SELECT region_name, turnout, CASE WHEN region_name = 'Вся Россия' THEN 'r' ELSE 'b' END AS color
    FROM
        (
            SELECT *
            FROM
            (
                SELECT region_id, ROUND(came * 1.0 / voters * 100, 2) AS turnout
                FROM president_elections_region
                WHERE year = {year} AND region_id <> (
                SELECT region_id
                FROM region
                WHERE region_name = 'Вся Россия'
            )
                ORDER BY turnout
                LIMIT 5
            ) best_ids
            UNION
            SELECT region_id, ROUND(came * 1.0 / voters * 100, 2) AS turnout
            FROM president_elections_region
            WHERE year = {year} AND region_id = (
                SELECT region_id
                FROM region
                WHERE region_name = 'Вся Россия'
            )
        ) AS region_ids
        INNER JOIN region USING(region_id)
        ORDER BY turnout;
    """, connection)
    fig1 = px.bar(top5_turnout, x='region_name', y='turnout', color='color',
                  title="Лучшие по явке регионы в выбранный год")
    fig2 = px.bar(worst5_turnout, x='region_name', y='turnout', color='color',
                  title="Худшие по явке регионы в выбранный год")
    fig1.update_yaxes(range=[50, 100])
    fig2.update_yaxes(range=[40, 100])
    return fig1, fig2


@callback(
    [Output('perc_results', 'figure'),
     Output('abs_results', 'figure'),
     Output('cand_top5', 'figure'),
     Output('cand_worst5', 'figure')],
    Input('p_candidate_dropdown', 'value')
)
def update_graph(candidate):
    connection = sqlite3.connect("elections.db")
    data1 = pd.read_sql_query(f"""
    SELECT pec.year || ' ' AS year, votes, ROUND(votes * 1.0 / voted * 100, 2) AS perc
    FROM 
        president_elections_cand AS pec
        INNER JOIN president_elections_region AS per ON pec.region_id = per.region_id AND pec.year = per.year
    WHERE candidate_id = (
        SELECT candidate_id
        FROM p_candidate
        WHERE candidate_name = '{candidate}'
    ) AND pec.region_id = (
        SELECT region_id
        FROM region
        WHERE region_name = 'Вся Россия'
    )
    ORDER BY pec.year
    """, connection)
    data2 = pd.read_sql_query(f"""
    SELECT region_name || ' ' || pec.year AS region_and_year, ROUND(votes * 1.0 / voted * 100, 2) AS perc
    FROM 
        president_elections_cand AS pec
        INNER JOIN president_elections_region AS per ON pec.region_id = per.region_id AND pec.year = per.year
        INNER JOIN region USING(region_id)
    WHERE candidate_id = (
        SELECT candidate_id
        FROM p_candidate
        WHERE candidate_name = '{candidate}'
    ) AND pec.region_id <> (
        SELECT region_id
        FROM region
        WHERE region_name = 'Вся Россия'
    )
    ORDER BY votes * 1.0 / voted DESC
    LIMIT 5
    """, connection)
    data3 = pd.read_sql_query(f"""
        SELECT region_name || ' ' || pec.year AS region_and_year, ROUND(votes * 1.0 / voted * 100, 2) AS perc
        FROM 
            president_elections_cand AS pec
            INNER JOIN president_elections_region AS per ON pec.region_id = per.region_id AND pec.year = per.year
            INNER JOIN region USING(region_id)
        WHERE candidate_id = (
            SELECT candidate_id
            FROM p_candidate
            WHERE candidate_name = '{candidate}'
        ) AND pec.region_id <> (
            SELECT region_id
            FROM region
            WHERE region_name = 'Вся Россия'
        )
        ORDER BY votes * 1.0 / voted
        LIMIT 5
        """, connection)
    fig1 = px.bar(data1, x='year', y='perc',
                  title="Результаты данного кандидата на всех выборах в процентном отношении")
    fig2 = px.bar(data1, x='year', y='votes',
                  title="Результаты данного кандидата на всех выборах в абсолютном отношении")
    fig3 = px.bar(data2, x='region_and_year', y='perc',
                  title="Лучшие результаты данного кандитата по регионам за все время")
    fig4 = px.bar(data3, x='region_and_year', y='perc',
                  title="Худшие результаты данного кандидата по регионам за все время")
    return fig1, fig2, fig3, fig4


if __name__ == '__main__':
    app.run(debug=True)
