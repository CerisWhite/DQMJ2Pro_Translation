from shuffle import randomize_and_patch,get_xp_curve_data
from nicegui import ui,app,run
from pathlib import Path
from randomInfo import RandomizationInfo
import os
import asyncio

STYLES={
    "dqmj2-button":"bg-blue-900 text-white rounded-lg border-2 border-black hover:bg-orange-400 !important",
    "dqmj2-element":"bg-blue-900 text-white rounded-lg border-2 border-black !important",
}

UPLOAD_DIR = Path(__file__).parent / 'temp_uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

output_dir= Path(__file__).parent / 'output'
xp_variance=[110]

randInfo=RandomizationInfo()


#Data change functions
def set_seed(value):
    try:
        randInfo.seed=int(value[:-2])
    except ValueError:
        randInfo.seed=0

def change_filter(key,value):
    if key in randInfo.filters:
        if value in randInfo.filters[key]:
            randInfo.filters[key].remove(value)
            if len(randInfo.filters[key])==0:
                randInfo.filters.pop(key,None)
        else:
            randInfo.filters[key].append(value)
    else:
        randInfo.filters[key]=[value]
    print("Current filters: "+ str(randInfo.filters))

def change_mods(value):
    if value in randInfo.mods:
        randInfo.mods.remove(value)
    else:
        randInfo.mods.append(value)
    print("Current mods: "+ str(randInfo.mods))

def change_level_up_mode(radio_value):
    match radio_value.value:
        case 1:
            randInfo.level_up_mode={}
        case 2:
            randInfo.level_up_mode={"swap":""}
        case 3:
            randInfo.level_up_mode={"random":xp_variance[0]}
    print("Current Level Up Mode="+str(randInfo.level_up_mode))

def change_skill_point_mode(radio_value):
    match radio_value.value:
        case 1:
            randInfo.skill_points_mode={}
        case 2:
            randInfo.skill_points_mode={"swap":""}
        case 3:
            randInfo.skill_points_mode={"random":""}
    print("Current Skill Point Mode="+str(randInfo.skill_points_mode))

def change_item_mode(value):
    if value == True:
        randInfo.item_mode={"swap":""}
    else:
        randInfo.item_mode={}
    print("Current Item Mode="+str(randInfo.item_mode))

def update_xp_chart(chart,value):
    chart._props['options'] = get_chart_opts(value/100)
    chart.update()
    xp_variance[0]=value
    if "random" in randInfo.level_up_mode.keys():
        randInfo.level_up_mode["random"]=xp_variance[0]
        print("Current Level Up Mode="+str(randInfo.level_up_mode))

async def uploaded(e):
    extension=e.file.name.split(".")[1]
    if extension=="nds":
        full_path = UPLOAD_DIR / "dqmj2.nds"

        with open(full_path, 'wb') as f:
            f.write(await e.file.read())
            f.flush()
    else:
        show_dialog(["Please import .nds file!\nAlso click on the check mark to remove the file and retry!"])

async def try_randomization():
    if Path("temp_uploads/dqmj2.nds").exists():
        with ui.dialog() as dialog, ui.card().classes("dqmj2-font"):
            ui.label("ROM is being randomized, please wait...")
            ui.spinner(size='lg')
            percent_label = ui.label("0% Complete!")
        dialog.open()

        try:
            await run.io_bound(randomize_and_patch, percent_label, randInfo)
            
            dialog.close()
            show_dialog(["ROM randomized successfully in output folder!"])
        except Exception as error:
            dialog.close()
            print(str(error))
            if str(error)=="no monsters":
                show_dialog(["This configuration leads to no monsters available. Please review your choices!"])
            else:
                show_dialog(["Cannot randomize ROM! Make sure you imported DMQJ2 ROM in its EU version!"])

    else:
        show_dialog(["Please import EU DQMJ2 .nds file!"])

def show_dialog(messages):
    with ui.dialog() as dialog,ui.card().classes("dqmj2-font"):
        for message in messages:
            ui.label(message)
        ui.button("OK",on_click=dialog.close)
    dialog.open()

def get_chart_opts(variance_factor):
    curves=get_xp_curve_data(variance_factor)
    return {
        "title": {"text": "XP Required by level (example)", "textStyle": {"color": "#ccc"}},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["Maximum", "Normal","Minimum"], "textStyle": {"color": "#ccc"}},
        "xAxis": {
            "type": "category",
            "data": curves["levels"],
            "axisLabel": {"color": "#ccc"},
        },
        "yAxis": {"type": "value", "axisLabel": {"color": "#ccc"}},
        "series": [
            {
                "name": "Normal",
                "type": "line",
                "data": curves["normal"],
                "itemStyle":{"color": "#dae908"},
                "lineStyle": {"width": 3,"color": "#dae908"},
                "symbol": "none",
                #"z": 10,
            },
            {
                "name": "Minimum",
                "type": "line",
                "data": curves["min"],
                "itemStyle":{"color": "#1e08e9"},
                "lineStyle": {"width": 3,"color": "#1e08e9"},
                "symbol": "none",
            },
            {
                "name": "Maximum",
                "type": "line",
                "data": curves["max"],
                "itemStyle":{"color": "#e90808"},
                "lineStyle": {"width": 3,"color": "#e90808"},
                "symbol": "none",
            },
        ],
    }

#Components

def monsters_tab(monsters):
    with ui.tab_panel(monsters).classes("bg-black"):
                with ui.checkbox("Allow Flee and Scout for all battles", value=True, on_change=lambda e: change_mods("always_flee")).classes(STYLES["dqmj2-button"]):
                    ui.tooltip("Make Flee and Scout options always available,even in boss fights").classes("bg-cyan")
                with ui.checkbox("Remove 0 XP monsters (such as arena monsters)", value=True, on_change=lambda e: change_filter("special","no_arena_monsters")).classes(STYLES["dqmj2-button"]):
                     ui.tooltip("Remove special monster such as arena monsters giving 0 XP and sometime 0 Gold").classes("bg-cyan")
                with ui.row():
                    with ui.checkbox("Randomize XP", value=False, on_change=lambda e: change_mods("random_xp")).classes(STYLES["dqmj2-button"]):
                        ui.tooltip("Each monster gives a random amount of XP").classes("bg-cyan")
                    ui.button(icon="help",on_click=lambda e:show_dialog(["How does XP Randomization works?",
                                                                         "",
                                                                         "Each monster has a chance of giving XP based on thresholds:",
                                                                         "0 to 100 XP => 54%",
                                                                         "100 to 1 000 XP => 30%",
                                                                         "1 000 to 10 000 XP => 10%",
                                                                         "10 000 to 100 000 XP => 5%",
                                                                         "100 000 to 333 333 XP => 1%"])).classes(STYLES["dqmj2-button"]+" rounded-xl")
                with ui.expansion('Filter Ranks', icon='font_download',caption="Include or exclude monster ranks you want").classes('w-full section-banner text-white rounded'):
                    with ui.row().classes('w-full'):
                        ui.checkbox("???", value=True, on_change=lambda e: change_filter("rank","???")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("X", value=True, on_change=lambda e: change_filter("rank","X")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("S", value=True, on_change=lambda e: change_filter("rank","S")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("A", value=True, on_change=lambda e: change_filter("rank","A")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("B", value=True, on_change=lambda e: change_filter("rank","B")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("C", value=True, on_change=lambda e: change_filter("rank","C")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("D", value=True, on_change=lambda e: change_filter("rank","D")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("E", value=True, on_change=lambda e: change_filter("rank","E")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("F", value=True, on_change=lambda e: change_filter("rank","F")).classes(STYLES["dqmj2-button"])

                with ui.expansion('Filter Families', icon='pets',caption="Include or exclude monster families you want").classes('w-full section-banner text-white rounded'):
                    with ui.row().classes('w-full'):
                        ui.checkbox("Beast", value=True, on_change=lambda e: change_filter("family","Beast")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Nature", value=True, on_change=lambda e: change_filter("family","Nature")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Dragon", value=True, on_change=lambda e: change_filter("family","Dragon")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Demon", value=True, on_change=lambda e: change_filter("family","Demon")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Undead", value=True, on_change=lambda e: change_filter("family","Undead")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Material", value=True, on_change=lambda e: change_filter("family","Material")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Slime", value=True, on_change=lambda e: change_filter("family","Slime")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Boss", value=True, on_change=lambda e: change_filter("family","Boss")).classes(STYLES["dqmj2-button"])

                with ui.expansion('Filter Size', icon='height',caption="Include or exclude monster sizes you want").classes('w-full section-banner text-white rounded'):
                    with ui.row().classes('w-full'):
                        ui.checkbox("Small", value=True, on_change=lambda e: change_filter("size","1")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Medium", value=True, on_change=lambda e: change_filter("size","2")).classes(STYLES["dqmj2-button"])
                        ui.checkbox("Giant", value=True, on_change=lambda e: change_filter("size","3")).classes(STYLES["dqmj2-button"])

def levelup_tab(level_up):
    with ui.tab_panel(level_up).classes("bg-black"):
                ui.radio({1: 'Do not randomize Level Up XP', 2: 'Swap Level Up XP curves', 3: 'Randomize Level Up XP (see below)'},value=1,on_change=lambda e:change_level_up_mode(e)).classes("bg-blue-900 text-white rounded-lg border-2 border-black")
                chart=ui.echart(options=get_chart_opts(1.1)).classes(STYLES["dqmj2-element"])
                slider = ui.slider(min=110, max=200, value=110,on_change=lambda e: update_xp_chart(chart,e.value)).classes(STYLES["dqmj2-element"])
                ui.label().bind_text_from(
                target_object=slider, 
                target_name='value', 
                backward=lambda v: f"Variation: {v} %"
                ).classes("text-white")

def skill_points_tab(skill_points):
    with ui.tab_panel(skill_points).classes("bg-black"):
         ui.radio({1: 'Do not randomize Skill Points', 2: 'Swap Skill Points Levels', 3: 'Randomize Skill Points'},value=1,on_change=lambda e:change_skill_point_mode(e)).classes("bg-blue-900 text-white rounded-lg border-2 border-black")

def challenge_tab(challenges):
    with ui.tab_panel(challenges).classes("bg-black"):
        with ui.checkbox("No flee challenge", value=False, on_change=lambda e: change_mods("no_flee")).classes(STYLES["dqmj2-button"]):
            ui.tooltip("Do not flee anymore! Win or loss is the only way!   This challenge is disabled if \"Allow Flee and Scout for all battles\" is enabled!").classes("bg-cyan")
        with ui.checkbox("Stronger monsters (50% stats raise)", value=False, on_change=lambda e: change_mods("150%_stats")).classes(STYLES["dqmj2-button"]):
            ui.tooltip("Monsters HP,MP,DEF,ATK,AGI and WIS are multiplied by 1.5").classes("bg-cyan")

def item_tab(items):
    with ui.tab_panel(items).classes("bg-black"):
        with ui.checkbox("Randomize Items", value=False, on_change=lambda e: change_item_mode(e.value)).classes(STYLES["dqmj2-button"]):
            ui.tooltip("Randomizes what every item in the game will do.").classes("bg-cyan")
@ui.page('/')
def root():
    app.add_static_files('/static', 'fonts')
    ui.add_head_html(r'''
    <style>
    @font-face{
        font-family: "depixelklein";
        src: url('/static/depixelklein.ttf') format('truetype');
        font-weight: normal;
        font-style: normal;
    }
    .dqmj2-font{
        font-family: 'depixelklein';
                      }
    .section-banner{
                     background: radial-gradient(#083973, #105aad);
                     font-color: white;
    }
    .custom-btn:hover {
            background: red !important;
        }
    .custom-btn:hover .q-focus-helper {
            background: #fc7e0f !important;
            opacity: 1 !important;
        }
    </style>
    ''')
    ui.query('body').style('background: radial-gradient(#bfbfbf, #636363); height: 100vh;')
    with ui.card().style("background: black;width: 100%").classes('text-center'):
        with ui.row():
            ui.label("DQMJ2 Randomizer").style("font-size: 40px;font-family: 'depixelklein'; color: white;")
            #ui.button("Close Randomizer",on_click=os.kill(os.getpid(), signal.SIGTERM))

    
    with ui.card().style("background:#5a5a5a;border-color: #bdbdbd;border-style: solid;border-width: 2px;width: 100%").classes('dqmj2-font'):
        with ui.row().classes("w-full"):
            ui.upload(auto_upload=True,label="Import EU DQMJ2 ROM:",max_files=1,on_upload=lambda e: uploaded(e))
            ui.number("Seed", value=0, precision=0,step=1, on_change=lambda e: set_seed(str(e.value))).style("background: white;")
        if Path("temp_uploads/dqmj2.nds").exists():
                ui.label("ROM already imported!").classes("text-green")
        with ui.checkbox("Generate Spoiler File", value=randInfo.generate_spoiler, on_change=lambda e: setattr(randInfo, 'generate_spoiler', e.value)).classes(STYLES["dqmj2-button"]):
                    ui.tooltip("Generate a spoiler file with the randomized information").classes("bg-cyan")
        with ui.tabs().classes('w-full') as tabs:
            monsters = ui.tab('Monsters').classes(STYLES["dqmj2-button"])
            level_up=ui.tab('Level Up').classes(STYLES["dqmj2-button"])
            skill_points=ui.tab("Skill Points").classes(STYLES["dqmj2-button"])
            items=ui.tab("Items").classes(STYLES["dqmj2-button"])
            challenges = ui.tab('Challenges').classes(STYLES["dqmj2-button"])
        with ui.tab_panels(tabs, value=monsters).classes('w-full'):
            monsters_tab(monsters)
            levelup_tab(level_up)
            skill_points_tab(skill_points)
            item_tab(items)
            challenge_tab(challenges)
            

    with ui.card().style("background:#5a5a5a;border-color: #bdbdbd;border-style: solid;border-width: 2px;width: 100%").classes('dqmj2-font'):
        with ui.row().classes("w-full"):
            ui.button("Randomize!", on_click=lambda: try_randomization()).classes('flex-1 text-white custom-btn '+ STYLES["dqmj2-button"])
            ui.button("Open output folder",on_click=lambda: os.startfile(output_dir)).classes("w-1/4 custom-btn "+STYLES["dqmj2-button"])
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(reload=False,title="DQMJ2 Randomizer")
