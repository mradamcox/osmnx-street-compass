import os
import json
from datetime import datetime
import argparse
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd
import geopandas as gpd

ox.config(log_console=True, use_cache=True)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input",
        help="input shapefile or a .json with a list of places"
    )
    parser.add_argument("-l","--label_field",
        help="name of the field that should be used for the label of each graph (shp input only)"
    )
    parser.add_argument("-t","--title",
        default="City Street Network Orientation",
        help="title for the output image"
    )
    parser.add_argument("--weight_by_length",
        action="store_true",
        help="weight the street bearing counts by length of street"
    )
    parser.add_argument("--save_network_images",
        action="store_true",
        help="export an image of each network that is used to create a compass graph"
    )
    parser.add_argument("--timestamp",
        action="store_true",
        help="add timestamp to the output image file"
    )
    args = parser.parse_args()
    
    return args

def reverse_bearing(x):
    return x + 180 if x < 180 else x - 180
    
def bearings_from_graph(G, weight_by_length=False):

    # calculate edge bearings
    Gu = ox.add_edge_bearings(ox.get_undirected(G))
    
    if weight_by_length:
        # weight bearings by length (meters)
        city_bearings = []
        for u, v, k, d in Gu.edges(keys=True, data=True):
            city_bearings.extend([d['bearing']] * int(d['length']))
        b = pd.Series(city_bearings)
        g_bearings = pd.concat([b, b.map(reverse_bearing)]).reset_index(drop='True')
    else:
        # don't weight bearings, just take one value per street segment
        b = pd.Series([d['bearing'] for u, v, k, d in Gu.edges(keys=True, data=True)])
        g_bearings = pd.concat([b, b.map(reverse_bearing)]).reset_index(drop='True')
        
    return g_bearings

def bearings_from_shapefile(shp_path,label_field,weight_by_length=False,save_network_images=False):
    
    bearings = {}
    shp_contents = gpd.read_file(shp_path)
    for name in shp_contents[label_field]:
        p = shp_contents[(shp_contents[label_field]==name)]
        polygon = p['geometry'].iloc[0]
        G = ox.graph_from_polygon(polygon, network_type='drive')
        bearings[name] = bearings_from_graph(G,weight_by_length=weight_by_length)
        
        if save_network_images:
            save_network_image(G,name)
    
    return bearings
    
def bearings_from_json(places,weight_by_length=False,save_network_images=False):
    
    bearings = {}
    for place in places.keys():
        query = places[place]
        G = ox.graph_from_place(query, network_type='drive')
        bearings[place] = bearings_from_graph(G,weight_by_length=weight_by_length)
        
        if save_network_images:
            save_network_image(G,place)
    
    return bearings

def save_network_image(G,name):

    G_projected = ox.project_graph(G)
    fig, ax = ox.plot_graph(G_projected,
        show=False,
        node_color='none',
        save=True,
        filename=name,
        file_format='png'
    )
    
    return

def count_and_merge(n, bearings):
    # make twice as many bins as desired, then merge them in pairs
    # prevents bin-edge effects around common values like 0° and 90°
    n = n * 2
    bins = np.arange(n + 1) * 360 / n
    count, _ = np.histogram(bearings, bins=bins)
    
    # move the last bin to the front, so eg 0.01° and 359.99° will be binned together
    count = np.roll(count, 1)
    return count[::2] + count[1::2]
    
# function to draw a polar histogram for a set of edge bearings
def polar_plot(ax, bearings, n=36, title=''):

    bins = np.arange(n + 1) * 360 / n
    count = count_and_merge(n, bearings)
    _, division = np.histogram(bearings, bins=bins)
    frequency = count / count.sum()
    division = division[0:-1]
    width =  2 * np.pi / n

    ax.set_theta_zero_location('N')
    ax.set_theta_direction('clockwise')

    x = division * np.pi / 180
    bars = ax.bar(x, height=frequency, width=width, align='center', bottom=0, zorder=2,
                  color='#003366', edgecolor='k', linewidth=0.5, alpha=0.7)
    
    ax.set_ylim(top=frequency.max())
    
    title_font = {'family':'Century Gothic', 'size':24, 'weight':'bold'}
    xtick_font = {'family':'Century Gothic', 'size':10, 'weight':'bold', 'alpha':1.0, 'zorder':3}
    ytick_font = {'family':'Century Gothic', 'size': 9, 'weight':'bold', 'alpha':0.2, 'zorder':3}
    
    ax.set_title(title.upper(), y=1.05, fontdict=title_font)
    
    ax.set_yticks(np.linspace(0, max(ax.get_ylim()), 5))
    yticklabels = ['{:.2f}'.format(y) for y in ax.get_yticks()]
    # yticklabels[0] = ''
    # empty out all of the y tick labels
    yticklabels = ['' for l in yticklabels]
    ax.set_yticklabels(labels=yticklabels, fontdict=ytick_font)
    
    xticklabels = ['N', '', 'E', '', 'S', '', 'W', '']
    ax.set_xticklabels(labels=xticklabels, fontdict=xtick_font)
    ax.tick_params(axis='x', which='major', pad=-2)

def compose_image(bearings,title="City Street Network Orientation",
        timestamp=False):
    
    # create figure and axes
    n = len(bearings)
    ncols = int(np.ceil(np.sqrt(n)))
    nrows = int(np.ceil(n / ncols))
    figsize = (ncols * 5, nrows * 5)
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, subplot_kw={'projection':'polar'})

    # plot each city's polar histogram
    for ax, place in zip(axes.flat, sorted(bearings.keys())):
        polar_plot(ax, bearings[place].dropna(), title=place)

    # add super title and save full image
    suptitle_font = {'family':'Century Gothic', 'fontsize':60, 'fontweight':'normal', 'y':1.07}
    fig.suptitle(title, **suptitle_font)
    # fig.tight_layout(rect=[0, 0, 1, 0.9])
    fig.subplots_adjust(hspace=.35)
    # fig.subplots_adjust(top=2)

    filename = 'images/{}.png'.format(title.lower().replace(" ","_"))

    if timestamp:
         ts = datetime.now().strftime("%m%d%Y-%H%M")
         filename = filename.replace(".png","_{}.png".format(ts))
    fig.savefig(filename, dpi=120, bbox_inches='tight')
    plt.close()
    
    return filename

def main():
    args = parse_args()
    print("input: {}".format(args.input))
    
    ext = os.path.splitext(args.input)[1].lower()
    if ext == ".json":
        
        with open(args.input,'r') as injson:
            places = json.loads(injson.read())
        places = places.get('places',None)
        if not places:
            raise KeyError("invalid file: can't find key \"places\" in "\
            "the input json")
        bearings = bearings_from_json(places,
            save_network_images=args.save_network_images,
            weight_by_length=args.weight_by_length
        )

    elif ext == ".shp":
        
        if not args.label_field:
            raise Exception("you must provide a field name to use as the "\
                "label for each feature's graph (FID is not a valid field "\
                "name in this case)")
        bearings = bearings_from_shapefile(args.input,args.label_field,
            save_network_images=args.save_network_images,
            weight_by_length=args.weight_by_length
        )
        
    else:
        raise TypeError("invalid file: input must be .json or .shp")

    compose_image(bearings,title=args.title,timestamp=args.timestamp)

if __name__ == '__main__':
    main()
