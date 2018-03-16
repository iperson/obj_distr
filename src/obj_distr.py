import random
from random import randint

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

rgb_cutoff  = 0.5   	#greyscale cut off for placing objects

class MyData(object):
	"""Container for data passed by the user.

	Attributes:
		num_copies: Number of copies to create.
		object_name: Name of the object to copy.
		surface_name: Name of surface to place inastances on.
		use_vcolor: Use surface vertex colors for instance placement. Default False.
		use_normal: Use surface normal to align objects instead of z-axis. Default False (z-axis).
	"""

def __init__(self, 
        object_name="", 
        surface=None, 
        num_copies=0, 
        seed=0,
        item_bvh_list=None, 
        use_vcolor=False,
        use_normal=False):
  self.object_name = object_name
  self.surface = surface
  self.num_copies = num_copies
  self.seed = seed
  self.item_bvh_list = item_bvh_list
  self.use_vcolor = use_vcolor
  self.use_normal = use_normal
		
def bake_tex_to_vert_col():
	"""Bake surface texture to vertex colors.
	"""
	bpy.context.space_data.context = 'RENDER'
	bpy.context.scene.render.use_bake_to_vertex_color = True
	bpy.context.scene.render.bake_type = 'TEXTURE'
	bpy.ops.object.bake_image()
	bpy.context.space_data.context = 'OBJECT'

def vertex_color_array(surface):
	"""Returns RGB values for each vertex
	"""
	color_layer = surface.data.vertex_colors.active
	if color_layer == None:
		print("error: Object has no color layer")
		
	# loops through each mesh polygon
	# each polygon has its own loop indices consisting of loops
	# a vertex might have several of these loops each containing color data
	# we take all the data and attach it to the vertex dictionary [vertex: [colors]]
	# something like that.. I forget..
	v_col_dic = {}
	i = 0
	for poly in surface.data.polygons:
		for idx in poly.loop_indices:
			loop = surface.data.loops[idx]
			v = loop.vertex_index
			color_list = v_col_dic.get(v, []) # get vertex from dictionary, if no exist, create empty array
			color_list.append(color_layer.data[i].color)
			v_col_dic[v] = color_list # append vertex color to vertex in dictionary
			i += 1

	vertex_average_color = []
	for _ in surface.data.vertices:
		vertex_average_color.append(0)

	for key, val in v_col_dic.items():
		# make average RGB
		col = 0.0
		for c in val:
			col += c[0]
		col = col / len(val)
		vertex_average_color[key] = col

	return vertex_average_color

def build_point_cloud(surface, use_vcolor=False):
	point_list = [] 		# [[coordinates],[normal],col]
	if use_vcolor:
		color_layer = surface.data.vertex_colors.active
		v_col_dic = {}
		i = 0
		for poly in surface.data.polygons:
			for idx in poly.loop_indices:
				loop = surface.data.loops[idx]
				v = loop.vertex_index
				color_list = v_col_dic.get(v, []) 
				color_list.append(color_layer.data[i].color) 
				v_col_dic[v] = color_list
				i += 1
		
		vertex_average_color = []
		for key, val in v_col_dic.items():
			# make average RGB
			col = 0
			for c in val:
				col += c[0]
			col = col / len(val)
			vertex_average_color.append((key,col))
		
		verts = surface.data.vertices
		for i, col in vertex_average_color:
			if col >= rgb_cutoff:
				point_list.append([verts[i].co, verts[i].normal, col])
	else:
		for v in surface.data.vertices:
			point_list.append([v.co, v.normal, 1.0])
	
	return point_list

def remove_from_scene(item):
	bpy.data.objects.remove(item, True)
	del item

def make_bvh(item):
	bm = bmesh.new()
	bm.from_mesh(item.data)
	bm.transform(item.matrix_world)
	item_bvh = BVHTree.FromBMesh(bm)
	bm.free()
	return item_bvh

def overlaps(target_bvh, item_bvh_list):
	for bvh in item_bvh_list:
		if target_bvh.overlap(bvh):
			return True
	return False

def make_copy(item, v_loc, v_normal, surface):
	#make copy of item
	new_item = item.copy()
	new_item.data = item.data
	#new item location
	new_item.matrix_world.translation = surface.matrix_world.to_translation() + v_loc
	#new item rotation
	dirVector = Vector(v_normal)
	new_item.rotation_mode = 'QUATERNION'
	my_quaternion = dirVector.to_track_quat('Z', 'Y')
	#reconstruct world matrix with new parameters
	#org_loc, org_rot, org_scale = new_item.matrix_world.decompose()
	#new_loc = Matrix.Translation(org_loc)
	new_rot = my_quaternion.to_matrix().to_4x4()   #org_rot.to_matrix().to_4x4()
	#new_scale = Matrix.Scale(org_scale[0],4,(1,0,0)) * Matrix.Scale(org_scale[1],4,(0,1,0)) * Matrix.Scale(org_scale[2],4,(0,0,1))
	
	#new_item.matrix_world = new_loc * new_rot * new_scale # can multiply new rotation right before original
	new_item.matrix_world = new_item.matrix_world * new_rot

	return new_item

def spawn(my_data, next_vert=0, random_spawn=False, cluster_spawn=False):
	if my_data.object_name is None:
		print("Please select object")
		return
	if my_data.surface is None:
		print("Please select surface")
		return

	my_data.item = bpy.data.objects[my_data.object_name]

	if random_spawn:
		if len(my_data.point_list) <= 0:
			return False

		#random number for vertex selection
		rnd_vert = randint(0, len(my_data.point_list) - 1)
	
		#if random number does not fall within greyscale of vertex
		#the point gets deleted and we return.
		#this way values closer to black are less likely to spawn objects
		rgb_rnd = random.uniform(0.0, 1.0)
		if my_data.point_list[rnd_vert][2] < rgb_rnd:
			del my_data.point_list[rnd_vert]
			return True

		#get random location from point cloud
		v_loc = my_data.point_list[rnd_vert][0]
		if my_data.use_normal:
			v_normal = my_data.point_list[rnd_vert][1]
		else:
			v_normal = ((0.0, 0.0, 1.0))

		#remove used point
		del my_data.point_list[rnd_vert]

	if cluster_spawn:
		v_loc = my_data.surface.data.vertices[next_vert].co
		if my_data.use_normal:
			v_normal = my_data.surface.data.vertices[next_vert].normal
		else:
			v_normal = ((0.0, 0.0, 1.0))

	#place item into the scene at random location
	new_item = make_copy(my_data.item, v_loc, v_normal, my_data.surface)
	new_item_bvh = make_bvh(new_item)
	if overlaps(new_item_bvh, my_data.item_bvh_list):
		del new_item_bvh
		remove_from_scene(new_item)
	else:
		bpy.context.scene.objects.link(new_item)
		my_data.item_bvh_list.append(new_item_bvh)

	return True

"""
def recursive_build(graphs, i):
	if graphs[i] is None:
		return None
	else:
		row = []
		row.extend(graphs[i])
		graphs[i] = None
		for r in row:
			temp = recursive_build(graphs, r)
			if temp is not None:
				row.extend(temp)
		return row
"""

# replaces recursive_build to get rid off recursion
def connect(graph, start=0):
	result = []
	if graph[start] is None:
		for i in range(len(graph)):
			if graph[i] is not None:
				result = graph[i]
				result.extend(graph[i])
				graph[i] = None
				break
	
	temp = result.copy()
	i = 0   # prevents going over the items again
	full = True # true until every row in the table is None
	while full:
		full = False
		# extend result until no more connected rows exist
		for t in temp[i:]:
			if graph[t] is not None:
				result.extend([t])
				result.extend(graph[t])
				graph[t] = None
				i += 1
				full = True
		temp = result.copy()
		
		# check for new connections and reset if found
		if not full:
			for g in graph:
				if g is not None:
					temp = g
					i = 0
					full = True
	return result

def graph_using_vertex_color(surface, seed):
	"""
	Generates a 2D array
	Columns are vertices in descending order
	Rows are all of the connected vertices to that vertex ([i]) (NOT TO EACH OTHER)
	"""
	edges = surface.data.edges
	vertices = surface.data.vertices
	v_colors = vertex_color_array(surface)
		
	graph = []
	for i in range(len(vertices)):
		graph.append([])
	
	for e in edges:
		v_1 = e.vertices[0]
		v_2 = e.vertices[1]
		graph[v_1].append(v_2)
		graph[v_2].append(v_1)
	
	# remove rows containing vertices outside of rgb range
	for i in range(len(graph)):		
		if v_colors[i] < rgb_cutoff:
			graph[i] = None
		else:
			for j in graph[i]:
				if v_colors[j] < rgb_cutoff:
					graph[i] = None
					break

	new_graph = connect(graph, seed)
	
	return new_graph

def graph_from_point(surface, seed):
	edges = surface.data.edges
	vertices = surface.data.vertices

	# initialize graph
	graph = []
	for _ in vertices:
		graph.append([])

	for e in edges:
		v_1 = e.vertices[0]
		v_2 = e.vertices[1]
		graph[v_1].append(v_2)
		graph[v_2].append(v_1)
	
	new_graph = connect(graph, seed)

	return new_graph

def start_clustered_placement(my_data):
	print("\nStarting Clustered placement...")
	point_list = None
	my_data.item_bvh_list = []

	if my_data.use_vcolor:
		point_list = graph_using_vertex_color(my_data.surface, my_data.seed)
	else:
		point_list = graph_from_point(my_data.surface, my_data.seed)
	
	for p in point_list:
		if spawn(my_data, next_vert=p, cluster_spawn=True):
			if len(my_data.item_bvh_list) == my_data.num_copies:
				break
	# clean up
	del my_data.item_bvh_list

def start_random_placement(my_data):
	print("\nStarting Random placement...")
	my_data.point_list = build_point_cloud(my_data.surface, my_data.use_vcolor)
	my_data.item_bvh_list = []  #bvh of all the copies in the scene

	while len(my_data.item_bvh_list) < my_data.num_copies:
		if not spawn(my_data, random_spawn=True): #stop if no more spawns
			break
	# clean up
	del my_data.item_bvh_list

#####################################################################
####### 						              UI  						           ########
#####################################################################

class OBJECT_PT_spawn_objects(bpy.types.Panel):
	"""Creates a Panel in the scene context of the properties editor"""
	bl_label = 'Object Scatter'
	bl_idname = 'OBJECT_myUI'
	bl_space_type = 'PROPERTIES'
	bl_region_type = 'WINDOW'
	bl_context = 'object'

	def draw(self, context):
		layout = self.layout
		scene = context.scene

		layout.prop_search(scene, 'object_name', scene, 'objects')
		layout.prop(scene, 'num_copies')
		layout.prop(scene, 'seed')
		layout.prop(scene, 'use_vcolor')
		layout.prop(scene, 'use_normal')
		layout.operator('object.bake_tvcol')
		layout.operator('object.start_random_placement')
		layout.operator('object.start_clustered_placement')


class OBJECT_OT_bake_tvcol(bpy.types.Operator):
	bl_label = 'Bake Vertex Color'
	bl_idname = 'object.bake_tvcol'
	bl_description = 'Bakes vertex color from texture'

	def execute(self, context):
		print("Bake surface texture to vertex color")
		bake_tex_to_vert_col()
		return {'FINISHED'}


class OBJECT_OT_cluster_spawn(bpy.types.Operator):
	bl_label = 'Start clustered placement!'
	bl_idname = 'object.start_clustered_placement'
	bl_description = 'Attempts to place objects next to each other on a selected surface'

	def execute(self, context):
		bpy.types.Scene.my_data = MyData
		my_data = bpy.types.Scene.my_data

		my_data.object_name = bpy.context.scene.object_name
		my_data.surface = bpy.context.selected_objects[0]
		my_data.num_copies = bpy.context.scene.num_copies
		my_data.use_vcolor = bpy.context.scene.use_vcolor
		my_data.use_normal = bpy.context.scene.use_normal
		my_data.seed = bpy.context.scene.seed

		start_clustered_placement(bpy.context.scene.my_data)
		return {'FINISHED'}


class OBJECT_OT_spawn(bpy.types.Operator):
	bl_label = 'Start random placement!'
	bl_idname = 'object.start_random_placement'
	bl_description = 'Randomly places objects on selected surface'

	def execute(self, context):
		bpy.types.Scene.my_data = MyData
		my_data = bpy.types.Scene.my_data

		my_data.object_name = bpy.context.scene.object_name
		my_data.surface = bpy.context.selected_objects[0]
		my_data.num_copies = bpy.context.scene.num_copies
		my_data.use_vcolor = bpy.context.scene.use_vcolor
		my_data.use_normal = bpy.context.scene.use_normal
		my_data.seed = bpy.context.scene.seed

		start_random_placement(bpy.context.scene.my_data)

		return {'FINISHED'}

#####################################################################
####### 					Register  						 ########
#####################################################################

def register():
	bpy.utils.register_module(__name__)

	bpy.types.Scene.num_copies = bpy.props.IntProperty(
		name = 'Copies', 
		min = 1,
		default = 1)
	bpy.types.Scene.seed = bpy.props.IntProperty(
		name = 'Seed', 
		min = 0,
		default = 0)
	bpy.types.Scene.object_name = bpy.props.StringProperty(
		name = 'Object')
	bpy.types.Scene.use_vcolor = bpy.props.BoolProperty(
		name = 'Use Vertex Color',
		description = 'If checked will use texture color for object placement. Black areas will have no ojbects, while white will have the most',
		default=False)
	bpy.types.Scene.use_normal = bpy.props.BoolProperty(
		name = 'Align To Normal',
		description = 'If checked will align object z axis to vertex normal',
		default = False)

def unregister():
	bpy.utils.register_module(__name__)

	del bpy.types.Scene.num_copies
	del bpy.types.Scene.seed
	del bpy.types.Scene.object_name
	del bpy.types.Scene.my_texture
	del bpy.types.Scene.use_vcolor
	del bpy.types.Scene.my_data

if __name__ == '__main__':
	register()
