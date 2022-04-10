# Copyright (c) 2009-2022 The Regents of the University of Michigan.
# Part of HOOMD-blue, released under the BSD 3-Clause License.

import hoomd
from hoomd.operation import _HOOMDBaseObject
from . import _hpmc
from hoomd.hpmc import integrate
from hoomd.data.parameterdicts import ParameterDict, TypeParameterDict
from hoomd.data.typeparam import TypeParameter
from hoomd.logging import log
import numpy
import json


class ShapeMove(_HOOMDBaseObject):
    """Base class for all shape moves.

    Args:
        move_probability (`float`): Probability of performing a shape move in
            in some way. See the  documentation of each derived class for a
            descrition of how this parameter is interpreted in the context of
            each shape move subclass.

    Note:
        This class should not be instantiated by users. The class can be used
        for `isinstance` or `issubclass` checks.
    """

    _suported_shapes = None

    def __init__(self, move_probability):
        # Set base parameter dict for all shape_moves
        param_dict = ParameterDict(move_probability=float(move_probability))
        self._param_dict.update(param_dict)

    def _attach(self):
        integrator = self._simulation.operations.integrator
        if not isinstance(integrator, integrate.HPMCIntegrator):
            raise RuntimeError("The integrator must be a HPMC integrator.")
        if not integrator._attached:
            raise RuntimeError("Integrator is not attached yet.")

        integrator_name = integrator.__class__.__name__
        if integrator_name in self._suported_shapes:
            self._move_cls = getattr(_hpmc,
                                     self.__class__.__name__ + integrator_name)
        else:
            raise RuntimeError("Integrator not supported")
        self._cpp_obj = self._move_cls(
            self._simulation.state._cpp_sys_def,
            self._simulation.operations.integrator._cpp_obj)
        super()._attach()


class Constant(ShapeMove):
    """Apply a transition to a specified shape, changing a particle shape by
    the same way every time the updater is called.

    Note:
        This is useful for calculating a specific transition probability and
        derived thermodynamic quantities.

    Args:
        shape_params (dict): Arguments defining the shape to transition to

    Examples::

        mc = hoomd.hpmc.integrate.ConvexPolyhedron(23456)
        tetrahedron_verts = [(1, 1, 1), (-1, -1, 1),
                             (1, -1, -1), (-1, 1, -1)]
        mc.shape["A"] = dict(vertices=tetrahedron_verts)
        cube_verts = [(1, 1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1),
                      (1, -1, -1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)])
        constant_move = shape_move.Constant(shape_params=cube_verts)

    Attributes:
        shape_params (dict): Arguments defining the shape to transition to

    See Also:
        hoomd.hpmc.integrate for required shape parameters.
    """

    def __init__(self, shape_params):
        self._param_dict.update(ParameterDict(shape_params=dict(shape_params)))


class ElasticShapeMove(ShapeMove):
    """Apply scale and shear shape moves to particles with an energy penalty.

    Args:
        move_probability (`float`): Fraction of scale to shear moves.

    Example::

        mc = hoomd.hpmc.integrate.ConvexPolyhedron(23456)
        verts = [(1, 1, 1), (-1, -1, 1), (1, -1, -1), (-1, 1, -1)]
        mc.shape["A"] = dict(vertices=verts)
        elastic_move = hoomd.hpmc.shape_move.ElasticShapeMove(0.5)
        elastic_move.stiffness = 100
        elastic_move.reference_shape["A"] = verts

    Attributes:
        stiffness (:py:mod:`hoomd.variant.Variant`): Shape stiffness against
            deformations.

        reference_shape (`TypeParameter` [``particle type``, `dict`]): Reference
            shape against to which compute the deformation energy.

        move_probability (`float`): Fraction of scale to shear moves.
    """

    _suported_shapes = {'ConvexPolyhedron', 'Ellipsoid'}

    def __init__(self, move_probability=1):

        super().__init__(move_probability)
        param_dict = ParameterDict(stiffness=hoomd.variant.Variant)
        self._param_dict.update(param_dict)

        typeparam_ref_shape = TypeParameter('reference_shape',
                                            type_kind='particle_types',
                                            param_dict=TypeParameterDict(
                                                dict, len_keys=1))
        self._add_typeparam(typeparam_ref_shape)

    def _attach(self):
        integrator = self._simulation.operations.integrator
        if isinstance(integrator, integrate.Ellipsoid):
            for shape in integrator.shape.items():
                if not numpy.allclose((shape["a"], shape["b"], shape["c"])):
                    raise ValueError("This updater only works when a=b=c.")
        else:
            super()._attach()


class PythonShapeMove(ShapeMove):
    """Apply custom shape moves to particles through a Python callback.

    Args:
        move_probability (`float`): Average fraction of shape parameters to
            change each timestep.

    Note:
        Parameters must be given for every particle type and must be between 0
        and 1. This class is limited to performing MC moves on the predefined
        shape parameters, it does not performs any consistency checks internally.
        Therefore, any shape constraint (e.g. constant volume, etc) must be
        performed within the callback.

    Example::

        mc = hoomd.hpmc.integrate.ConvexPolyhedron()
        mc.shape["A"] = dict(vertices=[(1, 1, 1), (-1, -1, 1),
                                       (1, -1, -1), (-1, 1, -1)])
        # example callback
        class ExampleCallback:
            def __init__(self):
                default_dict = dict(sweep_radius=0, ignore_statistics=True)
            def __call__(self, type, param_list):
                # do something with params and define verts
                return dict("vertices":verts, **self.default_dict))
        python_move = hpmc.shape_move.PythonShapeMove()
        python_move.callback = ExampleCallback()

    Attributes:
        callback (``callable`` [`str`, `list`], `dict` ]): The python function
            that will be called to perform custom shape moves on arbitrary shape
            parameters. The function must take the particle type and a list of
            parameters as arguments and return a dictionary with the shape
            definition whose keys **must** match the shape definition of the
            integrator:

                ``callable[[str, list], dict]``

            Note that there is no type validation of the callback.

        params (`TypeParameter` [``particle type``, `list`]): List of tunable
            parameters to be updated.

        move_probability (`float`): Average fraction of shape parameters to
            change each timestep.
    """

    _suported_shapes = {
        'ConvexPolyhedron', 'ConvexSpheropolyhedron', 'Ellipsoid'
    }

    def __init__(self, move_probability=1):

        super().__init__(move_probability)
        param_dict = ParameterDict(callback=object)
        self._param_dict.update(param_dict)

        typeparam_shapeparams = TypeParameter('params',
                                              type_kind='particle_types',
                                              param_dict=TypeParameterDict(
                                                  [float], len_keys=1))
        self._add_typeparam(typeparam_shapeparams)

    @log(category='object', requires_run=True)
    def type_params(self):
        """dict: Tunable parameters as dictionary. The particle types are the
                 keys of the dictionary.

        Example:
            >>> python_shape_move.type_params()
            {'A': [0.21, 0.33], 'B': [0.561, 0.331, 0.123]}
        """
        return self._cpp_obj.getTypeParams()


class VertexShapeMove(ShapeMove):
    """Apply shape moves where particle vertices are translated.

    Args:
        move_probability (float): Average fraction of vertices to change during
            each shape move.

    Note:
        Vertices are rescaled during each shape move to ensure that the shape
        maintains a constant volume. To preserve detail balance, the maximum
        step size is rescaled by volume**(1/3) every time a move is accepted.

    Note:
        The shape definition used corresponds to the convex hull of the
        vertices.

    Example::

        mc = hoomd.hpmc.integrate.ConvexPolyhedron(23456)
        cube_verts = [(1, 1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1),
                      (1, -1, -1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)])
        mc.shape["A"] = dict(vertices=numpy.asarray(cube_verts) / 2)
        vertex_move = shape_move.VertexShapeMove()
        vertex_move.volume["A"] = 1

    Attributes:
        move_probability (float): Average fraction of vertices to change during
            each shape move.

        volume (float): Volume of the particles to hold constant.
    """

    _suported_shapes = {'ConvexPolyhedron', 'ConvexSpheropolyhedron'}

    def __init__(self, move_probability=1):

        super().__init__(move_probability)

        typeparam_volume = TypeParameter('volume',
                                         type_kind='particle_types',
                                         param_dict=TypeParameterDict(
                                             float, len_keys=1))
        self._add_typeparam(typeparam_volume)
