"""Define the project's workflow logic and operation functions.

Execute this script directly from the command line, to view your project's
status, execute operations and submit them to a cluster. See also:

    $ python src/project.py --help
"""
import signac
from flow import FlowProject, directives
from flow.environment import DefaultSlurmEnvironment
import os


class MyProject(FlowProject):
    pass


class Borah(DefaultSlurmEnvironment):
    hostname_pattern = "borah"
    template = "borah.sh"

    @classmethod
    def add_args(cls, parser):
        parser.add_argument(
            "--partition",
            default="gpu",
            help="Specify the partition to submit to."
        )


class R2(DefaultSlurmEnvironment):
    hostname_pattern = "r2"
    template = "r2.sh"

    @classmethod
    def add_args(cls, parser):
        parser.add_argument(
            "--partition",
            default="shortgpuq",
            help="Specify the partition to submit to."
        )


class Fry(DefaultSlurmEnvironment):
    hostname_pattern = "fry"
    template = "fry.sh"

    @classmethod
    def add_args(cls, parser):
        parser.add_argument(
            "--partition",
            default="batch",
            help="Specify the partition to submit to."
        )

# Definition of project-related labels (classification)
@MyProject.label
def sampled(job):
    return job.doc.get("done")


@MyProject.label
def initialized(job):
    pass


@directives(executable="python -u")
@directives(ngpu=1)
@MyProject.operation
@MyProject.post(sampled)
def sample(job):
    import hoomd_polymers
    from hoomd_polymers.systems import Pack
    import hoomd_polymers.forcefields
    from hoomd_polymers.forcefields import OPLS_AA_PPS
    from hoomd_polymers.sim import Simulation
    from hoomd_polymers.molecules import PPS
    import mbuild as mb
    import foyer

    with job:
        print("JOB ID NUMBER:")
        print(job.id)

        if job.isfile("restart.gsd"):
            with gsd.hoomd.open(job.fn("restart.gsd")) as traj:
                init_snap = traj[0]
            with open(job.fn("forcefield.pickle"), "rb") as f:
                hoomd_ff = pickle.load(f)
        else:
            mol_obj = getattr(hoomd_polymers.molecules, job.sp.molecule)
            ff_obj = getattr(hoomd_polymers.forcefields, job.sp.forcefield)
            system_obj = getattr(hoomd_polymers.systems, job.sp.system)

            system = system_obj(
                    molecule=mol_obj,
                    n_mols=job.sp.n_molecules,
                    density=job.sp.density,
                    mol_kwargs=job.sp.mol_kwargs,
                    **job.sp.system_kwargs
            )

            system.apply_forcefield(
                    forcefield=ff_obj(),
                    make_charge_neutral=True,
                    remove_hydrogens=job.sp.remove_hydrogens,
                    remove_charges=job.sp.remove_charges
            )
            init_snap = system.hoomd_snapshot
            hoomd_ff = system.hoomd_forcefield

        job.doc.ref_distance = system.reference_distance
        job.doc.ref_mass = system.reference_mass
        job.doc.ref_energy = system.reference_energy

        sim = Simulation(
            initial_state=init_snap,
            forcefield=hoomd_ff,
            gsd_write_freq=job.sp.gsd_write_freq,
            gsd_file_name=job.fn("trajectory.gsd"),
            log_write_freq=job.sp.log_write_freq
            log_file_name=job.fn("sim_data.txt"),
        )
        sim.pickle_forcefield(job.fn("forcefield.pickle"))
        target_box = system.target_box*10/job.doc.ref_distance
        job.doc.target_box = target_box
        try:
            print("Running shrink simulation...")
            sim.run_update_volume(
                    final_box_lengths=target_box,
                    n_steps=job.sp.shrink_steps,
                    period=job.sp.shrink_period,
                    tau_kt=job.sp.tau_kt,
                    kT=job.sp.shrink_kT
            )
            sim.save_restart_gsd(job.fn("end_shrink.gsd"))
            print("Running NVT simulation...")
            sim.run_NVT(
                    kT=job.sp.kT,
                    n_steps=job.sp.n_steps,
                    tau_kt=job.sp.tau_kt
            )
            sim.save_restart_gsd(job.fn("restart.gsd"))
            job.doc.done = True
            job.doc.last_ts = sim.timestep
        except:
            sim.save_restart_gsd(job.fn("restart.gsd"))
            job.doc.last_ts = sim.timestep


if __name__ == "__main__":
    MyProject().main()
