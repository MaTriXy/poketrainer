# DISCLAIMER: This is jank
from flask import Flask, render_template, flash, redirect, url_for, abort
import json
import csv
from math import floor
from collections import defaultdict
import re
import argparse

from pgoapi.poke_utils import *
from pgoapi.utilities import *
import tempfile
import zerorpc
import os
from flask_socketio import SocketIO
app = Flask(__name__, template_folder="templates")
app.secret_key = ".t\x86\xcb3Lm\x0e\x8c:\x86\xe8FD\x13Z\x08\xe1\x04(\x01s\x9a\xae"

pokemon_names = json.load(open("pokemon.en.json"))
pokemon_details = {}
pokemon_lvls = {}
tcmpVals = []
options = {}
with open ("GAME_MASTER_POKEMON_v0_2.tsv") as tsv:
    reader = csv.DictReader(tsv, delimiter='\t')
    for row in reader:
        family_id = re.match("HoloPokemonFamilyId.V([0-9]*).*",row["FamilyId"]).group(1)
        pokemon_details[row["PkMn"]] = {
            "BaseStamina": float(row["BaseStamina"]),
            "BaseAttack": float(row["BaseAttack"]),
            "BaseDefense": float(row["BaseDefense"]),
            "CandyToEvolve": int(row["CandyToEvolve"]),
            "family_id": family_id
        }

attacks = {}
with open ("GAME_ATTACKS_v0_1.tsv") as tsv:
    reader = csv.DictReader(tsv, delimiter='\t')
    for row in reader:
        attacks[int(row["Num"])] = row["Move"]

with open ("PoGoPokeLvl.tsv") as tsv: #data gathered from here: https://www.reddit.com/r/TheSilphRoad/comments/4sa4p5/stardust_costs_increase_every_4_power_ups/
    reader = csv.DictReader(tsv, delimiter='\t')
    for row in reader:
        pokemon_lvls[float(row["TotalCpMultiplier"])] = {
            "DustSoFar": int(row["Stardust to this level"]),
            "CandySoFar": int(row["Candies to this level"]),
            "PokemonLvl": int(row["Pokemon level"]),
            "PowerUpResult": float(row["Delta(TCpM^2)"]),
            "TCPMDif": float(row["TCPM Difference"])
        }
        tcmpVals.append(float(row["TotalCpMultiplier"]))

def init_config():
    parser = argparse.ArgumentParser()
    config_file = "config.json"

    # If config file exists, load variables from json
    load = {}
    if os.path.isfile(config_file):
        with open(config_file) as data:
            load.update(json.load(data))

    # Read passed in Arguments
    required = lambda x: not x in load['accounts'][0].keys()
    parser.add_argument("-i", "--config_index", help="Index of account in config.json", default=0, type=int)
    config = parser.parse_args()
    load = load['accounts'][config.__dict__['config_index']]
    # Passed in arguments shoud trump
    for key,value in load.iteritems():
        if key not in config.__dict__ or not config.__dict__[key]:
            config.__dict__[key] = value

    return config.__dict__
config = init_config()



def setMaxCP(pokemon, maxTCPM):
    if not all_in(['cp', 'cp_multiplier', 'individual_stamina', 'individual_attack', 'individual_defense'], pokemon):
        pokemon['candyNeeded'] = 0
        pokemon['dustNeeded'] = 0
        pokemon['maxCP'] = 0
        pokemon['PowerUpResult'] = 0
        return

    candyToEvolve = pokemon_details[str(pokemon['pokemon_id'])]['CandyToEvolve']

    pokemon['candyNeeded'] = pokemon_lvls[maxTCPM]['CandySoFar'] - pokemon_lvls[pokemon['tcpm']]['CandySoFar'] + candyToEvolve
    pokemon['dustNeeded'] = pokemon_lvls[maxTCPM]['DustSoFar'] - pokemon_lvls[pokemon['tcpm']]['DustSoFar']

    family_id = pokemon_details[str(pokemon['pokemon_id'])]['family_id']
    maxPokeId = pokemon['pokemon_id']
    i = 0
    
    if pokemon['pokemon_id'] == 133: #is an Eevee
        if 'nickname' in pokemon and pokemon['nickname'] is 'Sparky':
            i = 2
        elif 'nickname' in pokemon and pokemon['nickname'] is 'Pyro': 
            i = 3
        else: #Rainer or Vaporean is the default
            i = 1
    else:
        while pokemon_details[str(pokemon['pokemon_id'] + i + 1)]['family_id'] == family_id and candyToEvolve > 0:
            candyToEvolve = pokemon_details[str(pokemon['pokemon_id'] + i + 1)]['CandyToEvolve']
            pokemon['candyNeeded'] += candyToEvolve
        i+=1

    if(i == 0):
        pokemon['maxCP'] = calcCP(pokemon, maxTCPM, pokemon_details)
    else:
        evolvedPoke = {}
        evolvedPoke['pokemon_id'] = pokemon['pokemon_id'] + i
        evolvedPoke['cp'] = pokemon['cp']
        evolvedPoke['cp_multiplier'] = pokemon['cp_multiplier']
        evolvedPoke['individual_defense'] = pokemon['individual_defense']
        evolvedPoke['individual_stamina'] = pokemon['individual_stamina']
        evolvedPoke['individual_attack'] = pokemon['individual_attack']

        pokemon['maxCP'] = calcCP(evolvedPoke, maxTCPM, pokemon_details)

    pokeLvl = pokemon_lvls[pokemon['tcpm']]['PokemonLvl']
    pokemon['PowerUpResult'] = calcCP(pokemon, tcmpVals[pokeLvl], pokemon_details) - pokemon['cp']

def setColumnsToIgnore(columnsToIgnore):
    options['ignore_recent'] = ''
    options['ignore_#'] = ''
    options['ignore_name'] = ''
    options['ignore_lvl'] = ''
    options['ignore_rating'] = ''
    options['ignore_IV'] = ''
    options['ignore_CP'] = ''
    options['ignore_max_CP'] = ''
    options['ignore_candies'] = ''
    options['ignore_candy_needed'] = ''
    options['ignore_dust_needed'] = ''
    options['ignore_power_up'] = ''
    options['ignore_stamina'] = ''
    options['ignore_attkIV'] = ''
    options['ignore_staIV'] = ''
    options['ignore_defIV'] = ''
    options['ignore_move1'] = ''
    options['ignore_move2'] = ''

    for column in columnsToIgnore:
        if column.lower() == 'recent':
            options['ignore_recent'] = 'display: none;'
        elif column.lower() == '#':
            options['ignore_id'] = 'display: none;'
        elif column.lower() == 'name':
            options['ignore_name'] = 'display: none;'
        elif column.lower() == 'lvl':
            options['ignore_lvl'] = 'display: none;'
        elif column.lower() == 'rating':
            options['ignore_rating'] = 'display: none;'
        elif column.lower() == 'iv':
            options['ignore_IV'] = 'display: none;'
        elif column.lower() == 'cp':
            options['ignore_CP'] = 'display: none;'
        elif column.lower() == 'max cp':
            options['ignore_max_CP'] = 'display: none;'
        elif column.lower() == 'candies':
            options['ignore_candies'] = 'display: none;'
        elif column.lower() == 'candy needed':
            options['ignore_candy_needed'] = 'display: none;'
        elif column.lower() == 'dust needed':
            options['ignore_dust_needed'] = 'display: none;'
        elif column.lower() == 'power up':
            options['ignore_power_up'] = 'display: none;'
        elif column.lower() == 'stamina':
            options['ignore_stamina'] = 'display: none;'
        elif column.lower() == 'att iv':
            options['ignore_attkIV'] = 'display: none;'
        elif column.lower() == 'sta iv':
            options['ignore_staIV'] = 'display: none;'
        elif column.lower() == 'def iv':
            options['ignore_defIV'] = 'display: none;'
        elif column.lower() == 'move 1':
            options['ignore_move1'] = 'display: none;'
        elif column.lower() == 'move 2':
            options['ignore_move2'] = 'display: none;'



@app.route("/<username>/pokemon")
def inventory(username):
    c = get_api_rpc(username)
    if c is None:
        return("There is no bot running with the input username!")
    options['DEFINE_POKEMON_LV'] = config.get("DEFINE_POKEMON_LV", "CP")
    options['IGNORE_COLUMNS'] = config.get("IGNORE_COLUMNS", [])
    setColumnsToIgnore(options['IGNORE_COLUMNS'])
    with open("data_dumps/%s.json"%username) as f:
        data = f.read()
        data = json.loads(data.encode())
        currency = data['GET_PLAYER']['player_data']['currencies'][1]['amount']
        latlng = c.current_location()
        latlng = "%f,%f" % (latlng[0],latlng[1])
        items = data['GET_INVENTORY']['inventory_delta']['inventory_items']
        pokemons = []
        candy = defaultdict(int)
        player = {}
        for item in items:
            item = item['inventory_item_data']
            pokemon = item.get("pokemon_data",{})
            if "pokemon_id" in pokemon:
                if 'nickname' in pokemon:
                    pokemon['name'] = str(pokemon['nickname'])
                else:
                pokemon['name'] = pokemon_names[str(pokemon['pokemon_id'])]
                pokemon.update(pokemon_details[str(pokemon['pokemon_id'])])
                pokemon['iv'] = pokemonIVPercentage(pokemon)
                pokemon['acpm'] = calcACPM(pokemon, pokemon_details)
                pokemon['tcpm'] = takeClosest((pokemon.get('cp_multiplier', 0) + pokemon['acpm']), tcmpVals) 
                pokemon['lvl'] = pokemon_lvls[pokemon['tcpm']]['PokemonLvl']
                #todo get rating
                pokemon['rating'] = 0
                pokemon['CalcCP'] = calcCP(pokemon, pokemon['tcpm'], pokemon_details)
                pokemons.append(pokemon)
            if 'player_stats' in item:
                player = item['player_stats']
            if "pokemon_family" in item:
                filled_family = str(item['pokemon_family']['family_id']).zfill(4)
                candy[filled_family] += item['pokemon_family'].get("candy",0)
        pokemons = sorted(pokemons, lambda x,y: cmp(x["iv"],y["iv"]),reverse=True)
        # add candy back into pokemon json
        for pokemon in pokemons:
            pokemon['candy'] = candy[pokemon['family_id']]
            setMaxCP(pokemon, tcmpVals[player['level']*2 + 1])
        player['username'] = data['GET_PLAYER']['player_data']['username']
        player['level_xp'] = player.get('experience',0)-player.get('prev_level_xp',0)
        player['hourly_exp'] = data.get("hourly_exp",0)
        player['goal_xp'] = player.get('next_level_xp',0)-player.get('prev_level_xp',0)
        return render_template('pokemon.html', pokemons=pokemons, player=player, currency="{:,d}".format(currency), candy=candy, latlng=latlng, attacks=attacks, options=options)


def get_api_rpc(username):
    desc_file = os.path.dirname(os.path.realpath(__file__))+os.sep+".listeners"
    sock_port = 0
    with open(desc_file) as f:
        data = f.read()
        data = json.loads(data.encode() if len(data) > 0 else '{}')
        if username not in data:
            print("There is no bot running with the input username!")
            return None
        sock_port = int(data[username])

    c = zerorpc.Client()
    c.connect("tcp://127.0.0.1:%i"%sock_port)
    return c

@app.route("/<username>/transfer/<p_id>")
def transfer(username, p_id):
    c = get_api_rpc(username)
    if c and c.releasePokemonById(p_id) == 1:
        flash("Released")
    else:
        flash("Failed!")
    return redirect(url_for('inventory', username = username))
if __name__ == "__main__":
    app.run(host='0.0.0.0',debug=True)
