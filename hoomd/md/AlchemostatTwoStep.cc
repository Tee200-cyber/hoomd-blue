// Copyright (c) 2009-2022 The Regents of the University of Michigan.
// Part of HOOMD-blue, released under the BSD 3-Clause License.

#include "AlchemostatTwoStep.h"

namespace hoomd
    {
namespace md
    {
namespace detail
    {

void export_AlchemostatTwoStep(pybind11::module& m)
    {
    pybind11::class_<AlchemostatTwoStep,
                     IntegrationMethodTwoStep,
                     std::shared_ptr<AlchemostatTwoStep>>(m, "AlchemostatTwoStep")
        .def(pybind11::init<std::shared_ptr<SystemDefinition>, unsigned int>())
        .def_property_readonly("period", &AlchemostatTwoStep::getAlchemTimeFactor)
        .def_property_readonly("alchemical_dof", &AlchemostatTwoStep::getAlchemicalParticleList)
        .def("setNextAlchemicalTimestep", &AlchemostatTwoStep::setNextAlchemicalTimestep);
    }

    } // namespace detail
    } // namespace md
    } // namespace hoomd
