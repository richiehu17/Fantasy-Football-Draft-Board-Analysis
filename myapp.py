import json
import requests

from bokeh.layouts import column
from bokeh.models import ColumnDataSource, CustomJS, DataTable
from bokeh.models.widgets import TableColumn, TextInput
from bokeh.plotting import curdoc
import numpy as np
import pandas as pd

league_id = 167859
year = 2022
url = f'https://fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{league_id}'

SWID = '{CA3E0FE5-48FA-4067-9A57-10331D2903CC}'
espn_s2 = 'AEA9sVLkJHdqHJIpBs2y%2BeGj47iqa8oqHYYAbPwHPdnoF5HWJcv8gUl8w7Jza5NDJoWKsGA4kK9JilY4N2VjBQE3LhCGqaU4xZZBGwnW9pX8zcI7X2wrR0VczNygAc%2Bg2pKCAAiz62IwFCyE99z0ht%2BJVKnhz8jp4BIcszHXfUEXuqGjWABa1Dz0oFp%2BGUoC0pXphjCF%2Fyf1iKtjYxM4cIkkfAZB2b9EmxnJpQvwUKVNKDmlEILfSVsIQfNFKgG7JyFc%2B%2FYLfKFf3RVBnm6cdEG8PrO4xrgO%2BaAOB9ErPy%2FEhg%3D%3D'

def get_points(pstats):
    current_stats = next((item for item in pstats if item['id'] == '002022'), None)
    if current_stats is None:
        avg_pts = 0.0
        total_pts = 0.0
    else:
        avg_pts = current_stats['appliedAverage']
        total_pts = current_stats['appliedTotal']

    return avg_pts, total_pts

position_map = {
    1: 'QB',
    2: 'RB',
    3: 'WR',
    4: 'TE',
    5: 'K',
    16: 'D/ST'
}

header_json = json.dumps({'players': {'limit': 2000, 'sortPercOwned': {'sortAsc': False, 'sortPriority': 1}}})

r = requests.get(url, params={'view': 'kona_player_info'}, headers={'x-fantasy-filter': header_json},
                 cookies={'swid': SWID, 'espn_s2': espn_s2})

players_json = r.json()['players']
players = []

for player in players_json:

    if 'stats' in player['player']:
        avg_pts, total_pts = get_points(player['player']['stats'])
    else:
        avg_pts = 0.0
        total_pts = 0.0

    players.append({'player_id': player['id'],
                    'name': player['player']['fullName'], 
                    'position': position_map[player['player']['defaultPositionId']],
                    'avg_pts': avg_pts,
                    'total_pts': total_pts})


# build position ranks 
players_df = pd.DataFrame(players)
players_df['avg_pts_rank'] = players_df.groupby('position')['avg_pts'].rank(method='average', ascending=False)
players_df['total_pts_rank'] = players_df.groupby('position')['total_pts'].rank(method='average', ascending=False)

r = requests.get(url, params={'view': 'mDraftDetail'},
                 cookies={'swid': SWID, 'espn_s2': espn_s2})

pick_order = r.json()['settings']['draftSettings']['pickOrder']

# building draft board
draft_dicts = []

for pick in r.json()['draftDetail']['picks']:
    draft_dicts.append({'player_id': pick['playerId'], 
                        'pick': pick['id'], 
                        'round': pick['roundId'], 
                        'round_pick': pick['roundPickNumber']})

draft_df = pd.DataFrame(draft_dicts)

info_df = pd.merge(players_df, draft_df, how='inner', on='player_id')
info_df.sort_values(by=['round', 'round_pick'], ascending=True, ignore_index=True, inplace=True)

# calculate draft order by position
info_df['position_draft'] = info_df.groupby('position')['pick'].rank(method='average', ascending=True).astype(int)
info_df['position_draft'] = info_df['position'] + ' ' + info_df['position_draft'].astype(str)
info_df['avg_pts_rank'] = np.where(info_df['avg_pts_rank'].astype(str).str[-1] == '5',
                                   info_df['position'] + ' ' + info_df['avg_pts_rank'].astype(str),
                                   info_df['position'] + ' ' + info_df['avg_pts_rank'].round(0).astype(int).astype(str))
info_df['total_pts_rank'] = np.where(info_df['total_pts_rank'].astype(str).str[-1] == '5',
                                     info_df['position'] + ' ' + info_df['total_pts_rank'].astype(str),
                                     info_df['position'] + ' ' + info_df['total_pts_rank'].round(0).astype(int).astype(str))
info_df['draft_board'] = np.where(info_df['position'] != 'D/ST', 
                                  info_df['pick'].astype(str) + '. ' + info_df['name'] + ', ' + info_df['position'],
                                  info_df['pick'].astype(str) + '. ' + info_df['name'])

info_map = info_df.set_index('draft_board').to_dict(orient='index')

# build draft board
rounds = 15
players = 14
draft_board_list = []
for i in range(rounds):
    min_pick = i * players
    max_pick = min_pick + 13
    picks = info_df.loc[min_pick:max_pick]['draft_board'].values.tolist()
    if i % 2 == 1:
        picks.reverse()
    # str_picks = [f'{pick[0]}. {pick[1]}, {pick[2]}' if pick[2] != 'D/ST' else f'{pick[0]}. {pick[1]}' for pick in picks]
    draft_board_list.append(picks)

# get team names and draft order
r = requests.get(url, cookies={'swid': SWID, 'espn_s2': espn_s2})

team_map = {}
for team in r.json()['teams']:
    team_map[team['id']] = f'{team["location"]} {team["nickname"]}'

pick_order_parsed = [team_map[pick] for pick in pick_order]
    
draft_board = pd.DataFrame(draft_board_list)
draft_board.columns = pick_order_parsed

source = ColumnDataSource(draft_board)
columns = [TableColumn(field=team, title=team) for team in pick_order_parsed]
data_table = DataTable(source=source, columns=columns, editable=False, autosize_mode='fit_viewport', index_position=None, sortable=False)

out_name = TextInput(value = '', title = 'Player:')
out_draft_info = TextInput(value = '', title = 'Drafted:')
out_avg_pts = TextInput(value = '', title = 'Average PPG Rank:')
out_total_pts = TextInput(value = '', title = 'Total PPG Rank:')
cell_row = TextInput(value = '', title = "Row:")
cell_col = TextInput(value = '', title = "Column:")


# source_code = """
# var grid = document.getElementsByClassName('grid-canvas')[0].children;
# var row, column = '';

# for (var i = 0,max = grid.length; i < max; i++){
#     if (grid[i].outerHTML.includes('active')){
#         row = i;
#         for (var j = 0, jmax = grid[i].children.length; j < jmax; j++)
#             if(grid[i].children[j].outerHTML.includes('active')) 
#                 { column = j }
#     }
# }
# rowtest.value = String(row);
# coltest.value = String(column);
# text_date.value = String(new Date(source.data['dates'][row]));
# text_downloads.value = String(source.data['downloads'][row]); 
# test_cell.value = column == 1 ? text_date.value : text_downloads.value; """

source_code = """
var grid = document.getElementsByClassName('grid-canvas')[0].children;
var row, column = '';

for (var i = 0,max = grid.length; i < max; i++){
    if (grid[i].outerHTML.includes('active')){
        row = i;
        for (var j = 0, jmax = grid[i].children.length; j < jmax; j++)
            if(grid[i].children[j].outerHTML.includes('active')) 
                { column = j }
    }
}
cell_row.value = String(row);
cell_col.value = String(column); """

def py_callback(attr, old, new):
    source.selected.update(indices = [])
    draft_value = draft_board.iat[int(cell_row.value), int(cell_col.value)]
    pick_info = info_map[draft_value]
    out_name.value = pick_info['name']
    out_draft_info.value = f'Pick {pick_info["pick"]}, {pick_info["position_draft"]}'
    out_avg_pts.value = pick_info['avg_pts_rank']
    out_total_pts.value = pick_info['total_pts_rank']

source.selected.on_change('indices', py_callback)
callback = CustomJS(args = dict(source = source, cell_row = cell_row, cell_col = cell_col), code = source_code)
source.selected.js_on_change('indices', callback)

# def function_source(attr, old, new):
#     try:
#         row = source.selected.indices[0]
#         # col = source.selected.indices[1]
#         rowtest.value = str(row)
#         print(source.selected.id)
#         print(source.selected.ref)
#         print(source.selected.struct)
#         # coltest.value = str(col)
#         # table_cell_column_1.value = str(source.data["dates"][selected_index])
#         # table_cell_column_2.value = str(source.data["downloads"][selected_index])
#     except IndexError:
#         pass

# source.selected.on_change('indices', function_source)
# curdoc().add_root(column(data_table, cell_row, cell_col))
curdoc().add_root(column(data_table, out_name, out_draft_info, out_avg_pts, out_total_pts))

