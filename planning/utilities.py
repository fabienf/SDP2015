from math import tan, pi
from Polygon.cPolygon import Polygon

def is_shot_blocked(world, angle_to_turn=0):
    """
    Checks if our robot could shoot past their robot
    """
    predicted_y = predict_y_intersection(
        world,  world.their_attacker.x, world.our_defender, full_width=False, bounce=True, angle_to_turn=angle_to_turn)
    if predicted_y is None:
        return True
    return abs(predicted_y - world.their_attacker.y) < world.their_attacker.length


def predict_y_intersection(world, predict_for_x, robot, full_width=False, bounce=False, angle_to_turn=0):
    """
    Predicts the (x, y) coordinates of the ball shot by the robot
    Corrects them if it's out of the bottom_y - top_y range.
    If bounce is set to True, predicts for a bounced shot
    Returns None if the robot is facing the wrong direction.
    """
    x = robot.x
    y = robot.y
    top_y = world.pitch.height - 60 if full_width else world.our_goal.y + (world.our_goal.width / 2) - 30
    bottom_y = 60 if full_width else world.our_goal.y - (world.our_goal.width / 2) + 30
    angle = robot.angle + angle_to_turn
    if (robot.x < predict_for_x and not (pi / 2 < angle < 3 * pi / 2)) or \
            (robot.x > predict_for_x and (3 * pi / 2 > angle > pi / 2)):
        if bounce:
            if not (0 <= (y + tan(angle) * (predict_for_x - x)) <= world.pitch.height):
                bounce_pos = 'top' if (y + tan(angle) * (predict_for_x - x)) > world.pitch.height else 'bottom'
                x += (world.pitch.height - y) / tan(angle) if bounce_pos == 'top' else (0 - y) / tan(angle)
                y = world.pitch.height if bounce_pos == 'top' else 0
                angle = (-angle) % (2 * pi)
        predicted_y = (y + tan(angle) * (predict_for_x - x))
        # Correcting the y coordinate to the closest y coordinate on the goal line:
        if predicted_y > top_y:
            return top_y
        elif predicted_y < bottom_y:
            return bottom_y
        return predicted_y
    else:
        return None


def is_wall_in_front(world):
    """
    Checks if there is a wall within the catcher area
    """
    cm_to_px = 3.7
    grabber_length= 6.7
    robot = world.our_defender
    zone = world.pitch.zones[world.our_defender.zone]
    x= centre_of_zone(world,world.our_defender)[0]
    y= centre_of_zone(world,world.our_defender)[1]

    #Extended area allows us to grab ball when it's on the line between zones

    # If we're on the left x values should be added
    if world.our_defender.zone == 0 or world.our_defender.zone== 2:
        top_edge= ((x+ world.pitch.width/2), y+ world.pitch.height/2)
        top_extended_point=  ((x+ (cm_to_px* grabber_length) + world.pitch.width/2), y+ world.pitch.height/2)
        bottom_extended_point= ((x+ (cm_to_px* grabber_length) + world.pitch.width/2), y - world.pitch.height/2)
        bottom_edge= ((x + world.pitch.width/2), y- world.pitch.height/ 2)
        extraArea= Polygon((top_edge, top_extended_point, bottom_extended_point, bottom_edge))
        extendedZone= zone | extraArea
        
    # otherwise x values should be subtracted
    else:
        top_edge= ((x- world.pitch.width/2), y+ world.pitch.height/2)
        top_extended_point=  ((x- (cm_to_px* grabber_length) - world.pitch.width/2), y+ world.pitch.height/2)
        bottom_extended_point= ((x- (cm_to_px* grabber_length) - world.pitch.width/2), y - world.pitch.height/2)
        bottom_edge= ((x - world.pitch.width/2), y- world.pitch.height/ 2)
        extraArea= Polygon((top_edge, top_extended_point, bottom_extended_point, bottom_edge))
        extendedZone= zone | extraArea


    grabber_area_left = robot.catcher_area_left
    outside_polygon_left= (extendedZone| grabber_area_left) - zone
    outside_area_left = int(outside_polygon_left.area())

    grabber_area_right= robot.catcher_area_right
    outside_polygon_right= (extendedZone| grabber_area_right) - zone
    outside_area_right = int(outside_polygon_left.area())
    
        if outside_area_left !=0 and outside_area_right != 0: 
            return "both"
        elif outside_area_left != 0:
            return "left"
        elif outside_area_right !=0:
            return "right"
        else:
            return None
    

def centre_of_zone(world, robot):
    """
    Given a robot calculate the centre of it's zone
    """
    zone_index = robot.zone
    zone_poly = world.pitch.zones[zone_index][0]

    min_x = int(min(zone_poly, key=lambda z: z[0])[0])
    max_x = int(max(zone_poly, key=lambda z: z[0])[0])

    x = min_x + (max_x - min_x) / 2
    y = world.pitch.height / 2
    return x, y
